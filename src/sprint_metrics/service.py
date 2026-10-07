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
import time
from urllib.parse import parse_qs, urlparse

from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs._internal import LogRecord
from opentelemetry.trace import StatusCode

from sprint_metrics.metrics import (
    ALL_METRICS,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_first_attempt_rate,
    calculate_throughput,
    calculate_wip_violations,
    metric_value,
)
from sprint_metrics.report import API_VERSION, format_json_report
from sprint_metrics.schema import EVENT_INTAKE_SCHEMA
from sprint_metrics.sprint_range import _parse_sprint_label, format_sprint_range_json
from sprint_metrics.store import (
    health_check,
    init_db,
    insert_event,
    query_all_sprints,
    query_range,
    query_sprint,
)
from sprint_metrics.telemetry import get_logger, get_tracer, init_telemetry

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

    init_telemetry()

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
            route = self.path.split("?")[0]
            status = 500
            tracer = get_tracer()
            with tracer.start_as_current_span(
                f"POST {route}",
                attributes={"http.method": "POST", "http.route": route},
            ) as span:
                try:
                    if self.path == "/schema/event":
                        self._send_json(405, {"error": "method not allowed"})
                        status = 405
                        return

                    if self.path != "/events":
                        self._send_json(404, {"error": "not found"})
                        status = 404
                        return

                    try:
                        content_length = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(content_length)
                        event = json.loads(body)
                    except (json.JSONDecodeError, ValueError):
                        self._send_json(400, {"error": "invalid JSON body"})
                        status = 400
                        return

                    for field in REQUIRED_FIELDS:
                        if field not in event:
                            self._send_json(400, {"error": f"missing required field: {field!r}"})
                            status = 400
                            return

                    event_type = event["type"]
                    if event_type not in VALID_EVENT_TYPES:
                        self._send_json(400, {"error": f"unknown event type: {event_type!r}"})
                        _emit_log(
                            SeverityNumber.ERROR,
                            f"event rejected: unknown type {event_type}",
                            {"card_id": event["card_id"], "event_type": event_type},
                        )
                        status = 400
                        return

                    card = event["card"]
                    if not isinstance(card, dict) or "created" not in card:
                        self._send_json(400, {"error": "card.created is required"})
                        status = 400
                        return

                    try:
                        insert_event(conn, event)
                    except Exception as exc:
                        self._send_json(500, {"error": f"database error: {exc}"})
                        status = 500
                        return

                    _emit_log(
                        SeverityNumber.INFO,
                        f"event accepted: card_id={event['card_id']} type={event_type}",
                        {"card_id": event["card_id"], "event_type": event_type},
                    )
                    self._send_json(200, {})
                    status = 200
                finally:
                    span.set_attribute("http.status_code", status)
                    span.set_status(StatusCode.OK if status < 400 else StatusCode.ERROR)

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?")[0]
            status = 500
            tracer = get_tracer()
            with tracer.start_as_current_span(
                f"GET {route}",
                attributes={"http.method": "GET", "http.route": route},
            ) as span:
                try:
                    if self.path.startswith("/sprint?label="):
                        label = self.path[len("/sprint?label=") :]
                        if not label:
                            self._send_json(400, {"error": "missing label parameter"})
                            status = 400
                            return
                        try:
                            cards = query_sprint(conn, label)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        body = _sprint_json(cards)
                        self._send_json(200, json.loads(body))
                        status = 200
                        return
                    elif self.path.startswith("/range?"):
                        parsed = urlparse(self.path)
                        params = parse_qs(parsed.query)
                        start = params.get("start", [""])[0]
                        end = params.get("end", [""])[0]
                        if not start or not end:
                            self._send_json(400, {"error": "missing start or end parameter"})
                            status = 400
                            return
                        try:
                            start_parsed = _parse_sprint_label(start)
                            end_parsed = _parse_sprint_label(end)
                        except ValueError as exc:
                            self._send_json(400, {"error": str(exc)})
                            status = 400
                            return
                        if start_parsed > end_parsed:
                            self._send_json(
                                400,
                                {"error": f"invalid range: start {start!r} is after end {end!r}"},
                            )
                            status = 400
                            return
                        try:
                            sprints = query_range(conn, start, end)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        labels = list(sprints.keys())
                        body = format_sprint_range_json(sprints, labels)
                        self._send_json(200, json.loads(body))
                        status = 200
                        return
                    elif self.path.startswith("/trend?"):
                        parsed = urlparse(self.path)
                        params = parse_qs(parsed.query)
                        metric = params.get("metric", [""])[0]
                        start = params.get("start", [""])[0]
                        end = params.get("end", [""])[0]
                        if not metric or not start or not end:
                            self._send_json(
                                400, {"error": "missing metric, start, or end parameter"}
                            )
                            status = 400
                            return
                        if metric not in ALL_METRICS:
                            self._send_json(400, {"error": f"unknown metric: {metric!r}"})
                            status = 400
                            return
                        try:
                            start_parsed = _parse_sprint_label(start)
                            end_parsed = _parse_sprint_label(end)
                        except ValueError as exc:
                            self._send_json(400, {"error": str(exc)})
                            status = 400
                            return
                        if start_parsed > end_parsed:
                            self._send_json(
                                400,
                                {"error": f"invalid range: start {start!r} is after end {end!r}"},
                            )
                            status = 400
                            return
                        try:
                            sprints = query_range(conn, start, end)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        values = [
                            {"sprint": label, "value": metric_value(metric, sprints[label])}
                            for label in sprints
                        ]
                        response = {
                            "api_version": API_VERSION,
                            "metric": metric,
                            "start": start,
                            "end": end,
                            "values": values,
                        }
                        self._send_json(200, response)
                        status = 200
                        return
                    elif self.path == "/metrics":
                        try:
                            sprints = query_all_sprints(conn)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        body = _metrics_text(sprints)
                        encoded = body.encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.end_headers()
                        self.wfile.write(encoded)
                        status = 200
                        return
                    elif self.path == "/schema/event":
                        self._send_json(200, EVENT_INTAKE_SCHEMA)
                        status = 200
                        return
                    elif self.path == "/health":
                        healthy = health_check(conn)
                        if healthy:
                            self._send_json(200, {"status": "ok"})
                            status = 200
                        else:
                            self._send_json(
                                503, {"status": "unavailable", "error": "database unreachable"}
                            )
                            status = 503
                        return
                    self._send_json(404, {"error": "not found"})
                    status = 404
                finally:
                    span.set_attribute("http.status_code", status)
                    span.set_status(StatusCode.OK if status < 400 else StatusCode.ERROR)

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


SERVICE_ENDPOINTS = (
    ("POST", "/events", "Accept a board event (started, blocked, unblocked, finished, escalated)"),
    ("GET", "/sprint", "Query a single sprint's metrics"),
    ("GET", "/range", "Query a range of sprints"),
    ("GET", "/trend", "Query a single metric's value across an inclusive sprint range"),
    ("GET", "/metrics", "Prometheus text exposition of stored history, sprint-labelled"),
    ("GET", "/schema/event", "JSON Schema for the event intake format"),
    ("GET", "/health", "Liveness/readiness check; 200 when the database is reachable"),
)


def _emit_log(severity: SeverityNumber, body: str, attributes: dict) -> None:
    """Emit a structured log record via the configured OpenTelemetry logger."""
    try:
        logger = get_logger()
        record = LogRecord(
            timestamp=int(time.time() * 1_000_000_000),
            observed_timestamp=None,
            severity_number=severity,
            severity_text=severity.name,
            body=body,
            event_name=None,
            attributes=attributes,
        )
        logger.emit(record)
    except Exception:
        pass
