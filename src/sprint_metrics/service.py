"""Long-lived HTTP service for the sprint-metrics package.

Accepts board events via POST /events and answers sprint queries via GET /sprint.
Requires a Postgres database (SPRINT_METRICS_DB).
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading

from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_failure_breakdown,
    calculate_first_attempt_rate,
    calculate_throughput,
    calculate_top_failure_causes,
    calculate_wip_violations,
)
from sprint_metrics.report import API_VERSION
from sprint_metrics.store import init_db, insert_event, query_sprint
from sprint_metrics.thresholds import calculate_flags

VALID_EVENT_TYPES = frozenset({"started", "blocked", "unblocked", "finished", "escalated"})
REQUIRED_FIELDS = ("api_version", "card_id", "type", "timestamp", "sprint", "card")


def run(db_url: str | None = None, port: int = 8080) -> int:
    """Start the service and block until interrupted. Returns the exit code.

    If db_url is None, reads SPRINT_METRICS_DB from the environment.
    Exits 1 with a stderr message if the database is unreachable.
    """
    if db_url is None:
        db_url = os.environ.get("SPRINT_METRICS_DB")
    if db_url is None:
        print(
            "sprint-metrics: SPRINT_METRICS_DB is not set; cannot connect to database",
            file=sys.stderr,
        )
        return 1

    try:
        import psycopg

        conn = psycopg.connect(db_url, connect_timeout=5)
    except Exception as exc:
        print(f"sprint-metrics: cannot connect to database: {exc}", file=sys.stderr)
        return 1

    try:
        init_db(conn)
    except Exception as exc:
        print(f"sprint-metrics: cannot initialise database schema: {exc}", file=sys.stderr)
        conn.close()
        return 1

    actual_port = _start_service(conn, port)
    print(f"sprint-metrics: service listening on http://0.0.0.0:{actual_port}", flush=True)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
    return 0


def _start_service(conn, port: int) -> int:
    """Start the HTTP server in a daemon thread and return the actual port."""

    class ServiceHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/events":
                self._send_json(404, {"error": "not found"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                event = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                self._send_json(400, {"error": "invalid JSON body"})
                return

            for field in REQUIRED_FIELDS:
                if field not in event:
                    self._send_json(400, {"error": f"missing required field: {field!r}"})
                    return

            event_type = event["type"]
            if event_type not in VALID_EVENT_TYPES:
                self._send_json(400, {"error": f"unknown event type: {event_type!r}"})
                return

            card = event["card"]
            if not isinstance(card, dict) or "created" not in card:
                self._send_json(400, {"error": "card.created is required"})
                return

            try:
                insert_event(conn, event)
            except Exception as exc:
                self._send_json(500, {"error": f"database error: {exc}"})
                return

            self._send_json(200, {})

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/sprint?label="):
                label = self.path[len("/sprint?label=") :]
                if not label:
                    self._send_json(400, {"error": "missing label parameter"})
                    return
                try:
                    cards = query_sprint(conn, label)
                except Exception as exc:
                    self._send_json(500, {"error": f"database error: {exc}"})
                    return
                body = _sprint_json(cards)
                self._send_json(200, json.loads(body))
                return
            self._send_json(404, {"error": "not found"})

        def _send_json(self, status: int, obj: dict) -> None:
            body = json.dumps(obj)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = http.server.HTTPServer(("0.0.0.0", port), ServiceHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return actual_port


def _sprint_json(cards) -> str:
    """Compute sprint metrics from stored cards and return the JSON report string."""
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards)
    blocked_aging = calculate_blocked_aging(cards)
    escalation_rate = calculate_escalation_rate(cards)
    first_attempt_rate = calculate_first_attempt_rate(cards)
    failure_breakdown = calculate_failure_breakdown(cards)
    top_causes = calculate_top_failure_causes(cards)
    flags = calculate_flags(cards, None, 0, None, None)

    report: dict[str, object] = {
        "api_version": API_VERSION,
        "cycle_time_days": cycle_time,
        "lead_time_days": lead_time,
        "throughput": throughput,
        "wip_violations": wip_violations,
        "blocked_aging_days": blocked_aging,
        "escalation_rate_percent": escalation_rate,
        "first_attempt_rate_percent": first_attempt_rate,
        "failure_breakdown": [
            {"class": cls, "role": role, "count": count} for cls, role, count in failure_breakdown
        ],
        "top_failure_causes": top_causes,
        "flags": flags,
    }
    return json.dumps(report)
