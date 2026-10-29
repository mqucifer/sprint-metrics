"""Long-lived HTTP service for the sprint-metrics package.

Accepts board events via POST /events and answers range and trend queries.
Requires a Postgres database (SPRINT_METRICS_DB).
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time
from collections.abc import Sequence
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs._internal import LogRecord
from opentelemetry.trace import StatusCode

from sprint_metrics.dora import (
    _RANGE_DORA_DESCRIPTION,
    _attach_range_dora,
    calculate_change_failure_and_mttr,
    calculate_dora_lead_time,
    calculate_release_frequency,
)
from sprint_metrics.metrics import (
    _RANGE_COST_DESCRIPTION,
    ALL_METRICS,
    _attach_range_cost,
    metric_value,
)
from sprint_metrics.report import API_VERSION
from sprint_metrics.rework import (
    _RANGE_REWORK_DESCRIPTION,
    _attach_range_rework,
    calculate_rework,
    calculate_sent_backs_count,
    extract_qa_returns,
)
from sprint_metrics.schema import EVENT_INTAKE_SCHEMA, TREND_SCHEMA
from sprint_metrics.sprint_range import (
    _RANGE_WINDOW_DESCRIPTION,
    _attach_range_window,
    _parse_sprint_label,
    format_sprint_range_json,
)
from sprint_metrics.store import (
    _RANGE_ROSTER_DESCRIPTION,
    _attach_range_roster,
    init_db,
    insert_event,
    query_card_kinds,
    query_dora_data,
    query_dora_rework_data,
    query_model_time_splits,
    query_range,
    query_returned_events,
    query_sprint,
    query_sprint_span,
    query_started_count,
    query_working_time_events,
    resolve_sprint_range,
    sprint_has_events,
    upsert_sprint,
)
from sprint_metrics.telemetry import get_logger, get_tracer, init_telemetry
from sprint_metrics.time_splits import (
    _RANGE_COST_BY_KIND_DESCRIPTION,
    _RANGE_IDLE_DESCRIPTION,
    _RANGE_MODEL_TIME_SPLIT_DESCRIPTION,
    _RANGE_WORKING_TIME_DESCRIPTION,
    _attach_range_cost_by_kind,
    _attach_range_idle,
    _attach_range_model_time_split,
    _attach_range_working_time,
    cost_by_kind_total,
    idle_minutes_total,
    model_time_split_total,
    working_time_total,
)
from sprint_metrics.verdict import (
    _RANGE_VERDICT_DESCRIPTION,
    _attach_range_standouts,
    _attach_range_verdict,
)

VALID_EVENT_TYPES = frozenset(
    {
        "started",
        "blocked",
        "unblocked",
        "finished",
        "escalated",
        "attempt_failed",
        "superseded",
        "returned",
    }
)
# Measures /trend once offered and now refuses with a 400 that says so.
RETIRED_TREND_METRICS = frozenset({"escalation_rate_percent", "escalation_count"})
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


USAGE = """\
usage: sprint-metrics

Start the sprint-metrics service on port 8080 against the Postgres database
named by SPRINT_METRICS_DB. The service takes no arguments.
"""

RETIRED_MESSAGE = (
    "sprint-metrics: the command-line report tool has been retired; "
    "start the service with no arguments and query it over HTTP"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the console script and ``python -m sprint_metrics``.

    With no arguments, starts the service. ``--help`` prints the usage; any
    other argument is a retired report option and is refused.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print(USAGE, end="")
        return 0
    if args:
        print(RETIRED_MESSAGE, file=sys.stderr)
        return 2
    return run()


def _start_service(conn, port: int, db_url: str = "") -> int:
    """Start the HTTP server in a daemon thread and return the actual port."""
    conn_holder = [conn]

    class ServiceHandler(http.server.BaseHTTPRequestHandler):
        def _ensure_db(self) -> bool:
            try:
                conn_holder[0].execute("SELECT 1")
                return True
            except Exception:
                pass
            if not db_url:
                return False
            import psycopg

            try:
                conn_holder[0] = psycopg.connect(db_url, connect_timeout=5)
                return True
            except Exception:
                return False

        def do_POST(self) -> None:  # noqa: N802
            route = self.path.split("?")[0]
            status = 500
            response_body = {}
            tracer = get_tracer()
            span = tracer.start_span(
                f"POST {route}",
                attributes={"http.method": "POST", "http.route": route},
            )
            try:
                if self.path == "/schema/event":
                    status, response_body = 405, {"error": "method not allowed"}
                    return

                if self.path == "/sprints":
                    try:
                        content_length = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(content_length)
                        sprint_data = json.loads(body)
                    except (json.JSONDecodeError, ValueError):
                        status, response_body = 400, {"error": "invalid JSON body"}
                        return

                    name = sprint_data.get("name")
                    if not isinstance(name, str) or not name:
                        status, response_body = (
                            400,
                            {"error": "missing or empty required field: 'name'"},
                        )
                        return

                    start_date_str = sprint_data.get("start_date", "")
                    try:
                        start_date = date.fromisoformat(start_date_str)
                    except (ValueError, TypeError):
                        status, response_body = (
                            400,
                            {"error": f"invalid start_date: {start_date_str!r}"},
                        )
                        return

                    end_date_str = sprint_data.get("end_date", "")
                    try:
                        end_date = date.fromisoformat(end_date_str)
                    except (ValueError, TypeError):
                        status, response_body = (
                            400,
                            {"error": f"invalid end_date: {end_date_str!r}"},
                        )
                        return

                    timezone = sprint_data.get("timezone")
                    if not isinstance(timezone, str) or not timezone:
                        status, response_body = (
                            400,
                            {"error": "missing or empty required field: 'timezone'"},
                        )
                        return

                    if not self._ensure_db():
                        status, response_body = (
                            503,
                            {
                                "status": "unavailable",
                                "error": "database temporarily unavailable",
                                "retryable": True,
                            },
                        )
                        return

                    try:
                        upsert_sprint(conn_holder[0], name, start_date, end_date, timezone)
                    except Exception as exc:
                        status, response_body = 500, {"error": f"database error: {exc}"}
                        return

                    status, response_body = 200, {"name": name}
                    return

                if self.path != "/events":
                    status, response_body = 404, {"error": "not found"}
                    return

                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    event = json.loads(body)
                except (json.JSONDecodeError, ValueError):
                    status, response_body = 400, {"error": "invalid JSON body"}
                    return

                for field in REQUIRED_FIELDS:
                    if field not in event:
                        status, response_body = (
                            400,
                            {"error": f"missing required field: {field!r}"},
                        )
                        return

                sprint_name = event.get("sprint")
                if not isinstance(sprint_name, str) or not sprint_name:
                    status, response_body = 400, {"error": "sprint must be a non-empty string"}
                    return

                event_type = event["type"]
                if event_type not in VALID_EVENT_TYPES:
                    _emit_log(
                        SeverityNumber.ERROR,
                        f"event rejected: unknown type {event_type}",
                        {"card_id": event["card_id"], "event_type": event_type},
                    )
                    status, response_body = (
                        400,
                        {"error": f"unknown event type: {event_type!r}"},
                    )
                    return

                card = event["card"]
                if not isinstance(card, dict) or "created" not in card:
                    status, response_body = 400, {"error": "card.created is required"}
                    return

                card_created_at = card.get("created_at")
                if card_created_at is not None and card_created_at != "":
                    if not isinstance(card_created_at, str):
                        status, response_body = (
                            400,
                            {"error": "card.created_at must be an ISO-8601 datetime string"},
                        )
                        return
                    try:
                        datetime.fromisoformat(card_created_at)
                    except ValueError:
                        status, response_body = (
                            400,
                            {
                                "error": f"card.created_at is not a valid ISO-8601 datetime: {card_created_at!r}"
                            },
                        )
                        return

                if event_type == "finished":
                    error = _validate_cost_fields(card)
                    if error:
                        status, response_body = 400, {"error": error}
                        return
                    error = _validate_model_time_split(card)
                    if error:
                        status, response_body = 400, {"error": error}
                        return

                if event_type == "superseded":
                    error = _validate_superseded_event(event)
                    if error:
                        status, response_body = 400, {"error": error}
                        return

                if not self._ensure_db():
                    status, response_body = (
                        503,
                        {
                            "status": "unavailable",
                            "error": "database temporarily unavailable",
                            "retryable": True,
                        },
                    )
                    return

                try:
                    insert_event(conn_holder[0], event)
                except Exception as exc:
                    status, response_body = 500, {"error": f"database error: {exc}"}
                    return

                _emit_log(
                    SeverityNumber.INFO,
                    f"event accepted: card_id={event['card_id']} type={event_type}",
                    {"card_id": event["card_id"], "event_type": event_type},
                )
                status, response_body = 200, {}
            finally:
                span.set_attribute("http.status_code", status)
                span.set_status(StatusCode.OK if status < 400 else StatusCode.ERROR)
                span.end()
                self._send_json(status, response_body)

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?")[0]
            status = 500
            tracer = get_tracer()
            with tracer.start_as_current_span(
                f"GET {route}",
                attributes={"http.method": "GET", "http.route": route},
            ) as span:
                try:
                    if route == "/sprint":
                        self._send_json(
                            410,
                            {
                                "error": (
                                    "endpoint removed: GET /sprint has been removed; "
                                    "use GET /range with a range spanning one sprint"
                                )
                            },
                        )
                        status = 410
                        return
                    elif route == "/metrics":
                        self._send_json(
                            410,
                            {
                                "error": (
                                    "endpoint removed: GET /metrics has been removed; "
                                    "use GET /range or GET /trend for the stored metrics"
                                )
                            },
                        )
                        status = 410
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
                            rework: dict[str, dict] = {}
                            for label in labels:
                                if label in has_events:
                                    rework[label] = calculate_rework(
                                        query_started_count(conn_holder[0], label),
                                        query_returned_events(conn_holder[0], label),
                                        extract_qa_returns(sprints[label]),
                                    )
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        body = format_sprint_range_json(sprints, labels)
                        result = json.loads(body)
                        _attach_range_window(result, labels, has_events)
                        _attach_range_cost(result, sprints, labels, has_events)
                        _attach_range_rework(result, labels, rework)
                        _attach_range_roster(result, conn_holder[0], labels, has_events)
                        _attach_range_dora(result, conn_holder[0], labels, has_events)
                        _attach_range_working_time(result, conn_holder[0], labels, has_events)
                        _attach_range_cost_by_kind(result, conn_holder[0], labels, has_events)
                        _attach_range_model_time_split(result, conn_holder[0], labels, has_events)
                        _attach_range_idle(result, conn_holder[0], labels, has_events)
                        _attach_range_verdict(result, labels, has_events)
                        _attach_range_standouts(result, labels, has_events)
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
                        if metric in RETIRED_TREND_METRICS:
                            self._send_json(
                                400,
                                {
                                    "error": (
                                        f"unknown metric: {metric!r} is no longer accepted; "
                                        "the escalation measures were removed"
                                    )
                                },
                            )
                            status = 400
                            return
                        if metric not in ALL_METRICS:
                            self._send_json(400, {"error": f"unknown metric: {metric!r}"})
                            status = 400
                            return
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
                            has_events: set[str] = set()
                            for label in sprints:
                                if sprint_has_events(conn_holder[0], label):
                                    has_events.add(label)
                        except Exception as exc:
                            self._send_json(500, {"error": f"database error: {exc}"})
                            status = 500
                            return
                        values = []
                        dora_data = None
                        dora_rework_data = None
                        if metric in ("release_frequency", "dora_lead_time_days"):
                            dora_data = query_dora_data(conn_holder[0], list(sprints.keys()))
                        if metric in (
                            "change_failure_count",
                            "change_failure_rate_percent",
                            "mean_time_to_recovery_minutes",
                        ):
                            dora_data = query_dora_data(conn_holder[0], list(sprints.keys()))
                            dora_rework_data = query_dora_rework_data(
                                conn_holder[0], list(sprints.keys())
                            )
                        for label in sprints:
                            if label not in has_events:
                                value = None
                            elif metric == "sent_backs_count":
                                returned = query_returned_events(conn_holder[0], label)
                                value = calculate_sent_backs_count(returned)
                            elif metric == "release_frequency":
                                released = dora_data["released_epics"].get(label)
                                value = calculate_release_frequency(released)
                            elif metric == "dora_lead_time_days":
                                spans = dora_data["story_spans_days"].get(label)
                                value = calculate_dora_lead_time(spans)
                            elif metric in (
                                "change_failure_count",
                                "change_failure_rate_percent",
                                "mean_time_to_recovery_minutes",
                            ):
                                cf_epics: list[str] | None = None
                                if dora_rework_data["epic_finished"]:
                                    cf_epics = [
                                        epic
                                        for epic, events in dora_rework_data["epic_finished"].items()
                                        if any(sprint == label for _t, sprint in events)
                                    ]
                                    if not cf_epics:
                                        cf_epics = []
                                cf = calculate_change_failure_and_mttr(
                                    cf_epics,
                                    label,
                                    dora_rework_data["epic_finished"],
                                    dora_rework_data["epic_returned"],
                                )
                                value = cf[metric]
                            elif metric == "working_time_minutes":
                                value = working_time_total(query_working_time_events(conn_holder[0], label))
                            elif metric in ("addition_working_time_minutes", "change_working_time_minutes"):
                                kind = "addition" if metric == "addition_working_time_minutes" else "change"
                                value = cost_by_kind_total(
                                    query_working_time_events(conn_holder[0], label),
                                    query_card_kinds(conn_holder[0], label),
                                    kind,
                                )
                            elif metric in (
                                "model_time_split_refinement_minutes",
                                "model_time_split_delivery_minutes",
                            ):
                                part = (
                                    "refinement"
                                    if metric == "model_time_split_refinement_minutes"
                                    else "delivery"
                                )
                                value = model_time_split_total(
                                    query_model_time_splits(conn_holder[0], label), part
                                )
                            elif metric == "idle_minutes":
                                value = idle_minutes_total(
                                    query_working_time_events(conn_holder[0], label),
                                    query_sprint_span(conn_holder[0], label),
                                )
                            else:
                                value = metric_value(metric, sprints[label])
                            values.append({"sprint": label, "value": value})
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

        def _end_transaction(self) -> None:
            """Roll back whatever transaction the request's reads left open.

            Writes commit themselves (insert_event, upsert_sprint), so this only
            ends read transactions, or a failed one. An idle connection then holds
            no lock on board_events, whichever path opened it, and init_db's
            ALTER TABLE in another session never waits on it.
            """
            try:
                from psycopg.pq import TransactionStatus

                if conn_holder[0].info.transaction_status != TransactionStatus.IDLE:
                    conn_holder[0].rollback()
            except Exception:
                pass

        def _send_json(self, status: int, obj: dict) -> None:
            self._end_transaction()
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


# The part of the /range description that is not specific to any one answer:
# the response's shape (the per-entry prior-sprint delta and the per-return
# semantics of failure_breakdown and top_failure_causes).
_RANGE_BASE_DESCRIPTION = (
    "Return metrics for a range of sprints in chronological order. "
    "Each entry includes the prior-sprint delta. "
    "failure_breakdown and top_failure_causes count returns, "
    "one per return, by (failure class, returning role). "
)

# One description fragment per /range answer, owned by its concern module, in
# the order the answers are laid out in the generated /range rows. Adding a new
# /range measure adds one fragment here and one row to the generated table.
_RANGE_ANSWER_DESCRIPTIONS = (
    _RANGE_WINDOW_DESCRIPTION,
    _RANGE_VERDICT_DESCRIPTION,
    _RANGE_COST_DESCRIPTION,
    _RANGE_REWORK_DESCRIPTION,
    _RANGE_ROSTER_DESCRIPTION,
    _RANGE_DORA_DESCRIPTION,
    _RANGE_WORKING_TIME_DESCRIPTION,
    _RANGE_COST_BY_KIND_DESCRIPTION,
    _RANGE_MODEL_TIME_SPLIT_DESCRIPTION,
    _RANGE_IDLE_DESCRIPTION,
)

# The composed /range description: the base plus every answer's fragment.
_RANGE_DESCRIPTION = _RANGE_BASE_DESCRIPTION + "".join(_RANGE_ANSWER_DESCRIPTIONS)


SERVICE_ENDPOINTS: list[tuple[str, str, str]] = [
    (
        "POST",
        "/sprints",
        "Register or update a sprint definition (name, start date, end date, timezone).",
    ),
    (
        "POST",
        "/events",
        "Accept a board event (started, blocked, unblocked, finished, escalated, "
        "attempt_failed, superseded, returned). The service validates the card's "
        "created date and event type.",
    ),
    (
        "GET",
        "/range",
        _RANGE_DESCRIPTION,
    ),
    (
        "GET",
        "/trend",
        "Return a single metric across a sprint range. "
        "Returns a JSON object with api_version and an ordered sequence of "
        "sprint-label-to-value pairs (the values array). "
        "Valid metrics: cycle_time_days, lead_time_days, throughput, "
        "wip_violations, blocked_aging_days, "
        "first_attempt_rate_percent, points_delivered, "
        "first_attempt_numerator, first_attempt_denominator, "
        "superseded_count, superseded_points, "
        "superseded_breakdown, cycle_time_minutes, lead_time_minutes, "
        "model_minutes_middle, model_minutes_total, "
        "input_tokens_middle, input_tokens_total, "
        "output_tokens_middle, output_tokens_total, "
        "cached_input_percent, reasoning_output_percent, "
        "sent_backs_count, release_frequency, dora_lead_time_days, "
        "change_failure_count, change_failure_rate_percent, "
        "mean_time_to_recovery_minutes, "
        "working_time_minutes, addition_working_time_minutes, "
        "change_working_time_minutes, "
        "model_time_split_refinement_minutes, "
        "model_time_split_delivery_minutes, "
        "idle_minutes. "
        "Minute-based metrics (cycle_time_minutes, lead_time_minutes) return "
        "JSON integer values in minutes (rounded); sprints with no events "
        "return JSON null. working_time_minutes returns the sprint's "
        "working-time total in whole minutes (null where the sprint has no "
        "closed session window). addition_working_time_minutes and "
        "change_working_time_minutes return the sprint's working time for "
        "stories of the given kind in whole minutes (null where the sprint "
        "carries no kind data). model_time_split_refinement_minutes and "
        "model_time_split_delivery_minutes return the sprint's model time "
        "split into refinement and delivery, in whole minutes (null where "
        "no story in the sprint carries a split). "
        "release_frequency returns the sprint's count of distinct epics "
        "released, in releases per sprint. dora_lead_time_days returns the "
        "mean lead time for changes, in whole days. "
        "change_failure_count and change_failure_rate_percent return the "
        "sprint's change-failure rate in whole percent (the rate is shown "
        "alongside its count). mean_time_to_recovery_minutes returns the "
        "mean time to recovery, in whole minutes. A sprint without a "
        "derivable DORA value (no events, or no epic link, or no epic "
        "release for the change-failure and recovery measures) returns "
        "JSON null. idle_minutes returns the sprint's idle time — the "
        "time that passed with no session running against the sprint's "
        "total registered duration — in whole minutes (null where the "
        "sprint is not registered or carries no session timestamps).",
    ),
    (
        "GET",
        "/schema/event",
        "Return the JSON Schema for the event intake body.",
    ),
    (
        "GET",
        "/health",
        'Health check. Returns 200 with {"status": "ok"} when the database '
        "is reachable, 503 otherwise.",
    ),
]


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




def _validate_cost_fields(card: dict) -> str | None:
    """Validate all-or-nothing cost fields on a finished event's card payload.

    Returns an error string on failure, None on success or when no cost key is present.
    """
    cost_keys = (
        "model_seconds",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    present = [k for k in cost_keys if k in card]
    if not present:
        return None
    missing = [k for k in cost_keys if k not in card]
    if missing:
        return f"partial cost payload on finished event: missing {', '.join(missing)}"
    for key in cost_keys:
        value = card[key]
        if isinstance(value, bool) or not isinstance(value, int):
            return f"invalid cost payload on finished event: {key} must be a non-negative integer"
        if value < 0:
            return f"invalid cost payload on finished event: {key} must be a non-negative integer"
    return None


def _validate_model_time_split(card: dict) -> str | None:
    """Validate all-or-nothing model-time split sub-object on a finished event's card payload.

    Returns an error string on failure, None on success or when no split key is present.
    """
    if "model_time_split" not in card:
        return None
    split = card["model_time_split"]
    if not isinstance(split, dict):
        return "invalid model-time split on finished event: must be an object"
    split_keys = ("refinement", "delivery")
    present = [k for k in split_keys if k in split]
    if not present:
        return None
    missing = [k for k in split_keys if k not in split]
    if missing:
        return f"partial model-time split on finished event: missing {', '.join(missing)}"
    for key in split_keys:
        value = split[key]
        if isinstance(value, bool) or not isinstance(value, int):
            return f"invalid model-time split on finished event: {key} must be a non-negative integer"
        if value < 0:
            return f"invalid model-time split on finished event: {key} must be a non-negative integer"
    return None


def _validate_superseded_event(event: dict) -> str | None:
    """Validate superseded-event-specific fields. Returns an error string or None."""
    if "because" in event and event["because"] not in ("sponsor", "story_problem"):
        return f"invalid because: {event['because']!r} (must be 'sponsor' or 'story_problem')"
    if "replaced_by" in event and not isinstance(event["replaced_by"], list):
        return "replaced_by must be an array of integers"
    return None
