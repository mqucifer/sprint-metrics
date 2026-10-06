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
from urllib.parse import parse_qs, urlparse

from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_first_attempt_rate,
    calculate_throughput,
    calculate_wip_violations,
)
from sprint_metrics.report import format_json_report
from sprint_metrics.sprint_range import _parse_sprint_label, format_sprint_range_json
from sprint_metrics.store import init_db, insert_event, query_all_sprints, query_range, query_sprint

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
            elif self.path.startswith("/range?"):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                start = params.get("start", [""])[0]
                end = params.get("end", [""])[0]
                if not start or not end:
                    self._send_json(400, {"error": "missing start or end parameter"})
                    return
                try:
                    start_parsed = _parse_sprint_label(start)
                    end_parsed = _parse_sprint_label(end)
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                if start_parsed > end_parsed:
                    self._send_json(
                        400, {"error": f"invalid range: start {start!r} is after end {end!r}"}
                    )
                    return
                try:
                    sprints = query_range(conn, start, end)
                except Exception as exc:
                    self._send_json(500, {"error": f"database error: {exc}"})
                    return
                labels = list(sprints.keys())
                body = format_sprint_range_json(sprints, labels)
                self._send_json(200, json.loads(body))
                return
            elif self.path == "/metrics":
                try:
                    sprints = query_all_sprints(conn)
                except Exception as exc:
                    self._send_json(500, {"error": f"database error: {exc}"})
                    return
                body = _metrics_text(sprints)
                encoded = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
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
    return format_json_report(cards)


def _metrics_text(sprints: dict[str, list]) -> str:
    """Format stored sprint history as Prometheus text exposition with sprint labels."""
    lines: list[str] = []
    for sprint_label, cards in sprints.items():
        cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
        throughput = calculate_throughput(cards)
        wip_violations = calculate_wip_violations(cards, None)
        blocked_aging = calculate_blocked_aging(cards, None)
        escalation_rate = calculate_escalation_rate(cards, 0)
        first_attempt_rate = calculate_first_attempt_rate(cards)

        label = f'sprint="{sprint_label}"'
        lines.append(f"sprint_cycle_time_days{{{label}}} {cycle_time}")
        lines.append(f"sprint_lead_time_days{{{label}}} {lead_time}")
        lines.append(f"sprint_throughput_cards{{{label}}} {throughput}")
        lines.append(f"sprint_wip_violations{{{label}}} {wip_violations}")
        lines.append(f"sprint_blocked_aging_days{{{label}}} {blocked_aging}")
        lines.append(f"sprint_escalation_rate_percent{{{label}}} {escalation_rate}")
        lines.append(f"sprint_first_attempt_rate_percent{{{label}}} {first_attempt_rate}")

    return "\n".join(lines)
