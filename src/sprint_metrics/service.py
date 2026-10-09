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
from datetime import date
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
from sprint_metrics.schema import EVENT_INTAKE_SCHEMA, TREND_SCHEMA
from sprint_metrics.sprint_range import _parse_sprint_label, format_sprint_range_json
from sprint_metrics.store import (
    init_db,
    insert_event,
    query_all_sprints,
    query_range,
    query_sprint,
    resolve_sprint_range,
    sprint_has_events,
    upsert_sprint,
)
from sprint_metrics.telemetry import get_logger, get_tracer, init_telemetry

VALID_EVENT_TYPES = frozenset(
    {"started", "blocked", "unblocked", "finished", "escalated", "attempt_failed"}
)
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

    actual_port = _start_service(conn, port, db_url)
    print(f"sprint-metrics: service listening on http://0.0.0.0:{actual_port}", flush=True)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
    return 0


def _start_service(conn, port: int, db_url: str = "") -> int:
    """Start the HTTP server in a daemon thread and return the actual port."""
    conn_holder = [conn]

    class ServiceHandler(http.server.BaseHTTPRequestHandler):
        def _ensure_db(self) -> bool:
            import psycopg

            try:
                conn_holder[0].execute("SELECT 1")
                return True
            except Exception:
                pass
            if not db_url:
                return False
            try:
                conn_holder[0] = psycopg.connect(db_url, connect_timeout=5)
                return True
            except Exception:
                return False

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

                    if self.path == "/sprints":
                        try:
                            content_length = int(self.headers.get("Content-Length", 0))
                            body = self.rfile.read(content_length)
                            sprint_data = json.loads(body)
                        except (json.JSONDecodeError, ValueError):
                            self._send_json(400, {"error": "invalid JSON body"})
                            status = 400
                            return

                        name = sprint_data.get("name")
                        if not isinstance(name, str) or not name:
                            self._send_json(
                                400, {"error": "missing or empty required field: 'name'"}
                            )
                            status = 400
                            return

                        start_date_str = sprint_data.get("start_date", "")
                        try:
                            start_date = date.fromisoformat(start_date_str)
                        except (ValueError, TypeError):
                            self._send_json(
                                400, {"error": f"invalid start_date: {start_date_str!r}"}
                            )
                            status = 400
                            return

                        end_date_str = sprint_data.get("end_date", "")
                        try:
                            end_date = date.fromisoformat(end_date_str)
                        except (ValueError, TypeError):
                            self._send_json(400, {"error": f"invalid end_date: {end_date_str!r}"})
                            status = 400
                            return

                        timezone = sprint_data.get("timezone")
                        if not isinstance(timezone, str) or not timezone:
                            self._send_json(
                                400, {"error": "missing or empty required field: 'timezone'"}
                            )
                            status = 400
                            return

                        if not self._ensure_db():
                            self._send_json(
                                503,
                                {
                                    "status": "unavailable",
                                    "error": "database temporarily unavailable",
                                    "retryable": True,
                                },
                            )
                            status = 503
                            return

                        try:
                            upsert_sprint(conn_holder[0], name, start_date, end_date, timezone)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return

                        self._send_json(200, {"name": name})
                        status = 200
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

                    sprint_name = event.get("sprint")
                    if not isinstance(sprint_name, str) or not sprint_name:
                        self._send_json(400, {"error": "sprint must be a non-empty string"})
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

                    if not self._ensure_db():
                        self._send_json(
                            503,
                            {
                                "status": "unavailable",
                                "error": "database temporarily unavailable",
                                "retryable": True,
                            },
                        )
                        status = 503
                        return

                    try:
                        insert_event(conn_holder[0], event)
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
                        if not self._ensure_db():
                            self._send_json(
                                503,
                                {
                                    "status": "unavailable",
                                    "error": "database temporarily unavailable",
                                    "retryable": True,
                                },
                            )
                            status = 503
                            return
                        try:
                            if not sprint_has_events(conn_holder[0], label):
                                self._send_json(200, _null_sprint_response())
                                status = 200
                                return
                            cards = query_sprint(conn_holder[0], label)
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
                        # Quick calendar validation (no DB needed) preserves 400 for
                        # invalid YYYY-MM ranges even when the DB is unreachable.
                        try:
                            _start_parsed = _parse_sprint_label(start)
                            _end_parsed = _parse_sprint_label(end)
                            if _start_parsed > _end_parsed:
                                self._send_json(
                                    400,
                                    {
                                        "error": f"invalid range: start {start!r} is after end {end!r}"
                                    },
                                )
                                status = 400
                                return
                        except ValueError:
                            pass
                        if not self._ensure_db():
                            self._send_json(
                                503,
                                {
                                    "status": "unavailable",
                                    "error": "database temporarily unavailable",
                                    "retryable": True,
                                },
                            )
                            status = 503
                            return
                        try:
                            resolved = resolve_sprint_range(conn_holder[0], start, end)
                        except ValueError as exc:
                            self._send_json(400, {"error": str(exc)})
                            status = 400
                            return
                        try:
                            if resolved is not None:
                                sprints = {}
                                for label in resolved:
                                    sprints[label] = query_sprint(conn_holder[0], label)
                                labels = resolved
                            else:
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
                                        {
                                            "error": f"invalid range: start {start!r} is after end {end!r}"
                                        },
                                    )
                                    status = 400
                                    return
                                sprints = query_range(conn_holder[0], start, end)
                                labels = list(sprints.keys())
                            has_events: set[str] = set()
                            for label in labels:
                                if sprint_has_events(conn_holder[0], label):
                                    has_events.add(label)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        body = format_sprint_range_json(sprints, labels)
                        result = json.loads(body)
                        for i, label in enumerate(labels):
                            if label not in has_events:
                                result["sprints"][label] = _null_range_entry()
                            elif i > 0 and labels[i - 1] not in has_events:
                                result["sprints"][label]["prior"] = None
                                result["sprints"][label]["delta"] = None
                        self._send_json(200, result)
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
                        # Quick calendar validation (no DB needed)
                        try:
                            _start_parsed = _parse_sprint_label(start)
                            _end_parsed = _parse_sprint_label(end)
                            if _start_parsed > _end_parsed:
                                self._send_json(
                                    400,
                                    {
                                        "error": f"invalid range: start {start!r} is after end {end!r}"
                                    },
                                )
                                status = 400
                                return
                        except ValueError:
                            pass
                        if not self._ensure_db():
                            self._send_json(
                                503,
                                {
                                    "status": "unavailable",
                                    "error": "database temporarily unavailable",
                                    "retryable": True,
                                },
                            )
                            status = 503
                            return
                        try:
                            resolved = resolve_sprint_range(conn_holder[0], start, end)
                        except ValueError as exc:
                            self._send_json(400, {"error": str(exc)})
                            status = 400
                            return
                        try:
                            if resolved is not None:
                                sprints = {}
                                for label in resolved:
                                    sprints[label] = query_sprint(conn_holder[0], label)
                            else:
                                try:
                                    start_parsed = _parse_sprint_label(start)
                                    end_parsed = _parse_sprint_label(end)
                                except ValueError as exc:
                                    self._send_json(400, {"error": str(exc)})
                                    status = 400
                                    return
                                sprints = query_range(conn_holder[0], start, end)
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
                        self._ensure_db()
                        try:
                            sprints = query_all_sprints(conn_holder[0])
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
                    elif self.path == "/schema/trend":
                        self._send_json(200, TREND_SCHEMA)
                        status = 200
                        return
                    elif self.path == "/health":
                        if self._ensure_db():
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
    ("POST", "/sprints", "Register a sprint definition (name, start_date, end_date, timezone)"),
    (
        "POST",
        "/events",
        "Accept a board event (started, blocked, unblocked, finished, escalated, attempt_failed)",
    ),
    ("GET", "/sprint", "Query a single sprint's metrics"),
    ("GET", "/range", "Query a range of sprints"),
    (
        "GET",
        "/trend",
        "Return a time series for a single metric across an inclusive sprint range "
        "as a JSON object with api_version and an ordered sequence of sprint-label-to-value pairs "
        "(params: metric, start, end); sprints with no stored events return the metric's zero value",
    ),
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


def _null_sprint_response() -> dict:
    """Return the null-filled response for a sprint with no stored events."""
    return {
        "api_version": API_VERSION,
        "cycle_time_days": None,
        "lead_time_days": None,
        "throughput": None,
        "wip_violations": None,
        "blocked_aging_days": None,
        "escalation_rate_percent": None,
        "first_attempt_rate_percent": None,
        "failure_breakdown": None,
        "top_failure_causes": None,
        "flags": None,
    }


def _null_range_entry() -> dict:
    """Return the null-filled per-sprint entry for a range response."""
    return {
        "cycle_time_days": None,
        "lead_time_days": None,
        "throughput": None,
        "wip_violations": None,
        "blocked_aging_days": None,
        "escalation_rate_percent": None,
        "first_attempt_rate_percent": None,
        "failure_breakdown": None,
        "top_failure_causes": None,
        "flags": None,
        "prior": None,
        "delta": None,
    }
