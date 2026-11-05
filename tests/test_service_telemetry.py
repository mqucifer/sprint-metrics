"""Service tests for the OpenTelemetry spans and log records."""

from __future__ import annotations

from service_helpers import (
    SPRINT_METRICS_DB,
    _clean_board_events,  # noqa: F401 (autouse: empties the tables)
    _make_event,
    _post_events,
    requires_db,
)

from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


class _InMemoryLogExporter:
    """Minimal in-memory log exporter for testing (opentelemetry-sdk lacks one)."""

    def __init__(self):
        self._logs = []

    def export(self, logs):
        self._logs.extend(logs)

    def flush(self):
        pass

    def shutdown(self):
        pass

    def get_finished_logs(self):
        return list(self._logs)


@requires_db
def test_service_works_without_otel_endpoint(monkeypatch, capsys):
    """AC3: endpoint not set → service responds 200, no error key, no ConnectionError on stderr."""
    import psycopg

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    init_telemetry()

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_telemetry'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac3_telemetry")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        captured = capsys.readouterr()
        assert "ConnectionError" not in captured.err
        assert "connection refused" not in captured.err
    finally:
        conn.close()


@requires_db
def test_post_events_span_name_and_attributes(monkeypatch):
    """AC1: POST /events → exactly one span named 'POST /events' with http.method and http.route."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_span'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_span")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        spans = exporter.get_finished_spans()
        matching = [s for s in spans if "POST" in s.name and "/events" in s.name]
        assert len(matching) == 1
        span = matching[0]
        assert span.attributes["http.method"] == "POST"
        assert span.attributes["http.route"] == "/events"
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_span_error_status(monkeypatch):
    """AC3: POST /events with invalid type 'frobnicated' → span status is not OK."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400

        spans = exporter.get_finished_spans()
        matching = [s for s in spans if "POST" in s.name and "/events" in s.name]
        assert len(matching) == 1
        span = matching[0]
        assert span.status.status_code != StatusCode.OK
    finally:
        conn.close()


@requires_db
def test_post_valid_event_emits_info_log_record(monkeypatch):
    """AC1: valid POST /events → in-memory log exporter has a record with severity INFO,
    body includes card_id and event type."""
    import psycopg
    from opentelemetry._logs import SeverityNumber

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    log_exporter = _InMemoryLogExporter()
    init_telemetry(log_exporter=log_exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="c1", event_type="started")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        logs = log_exporter.get_finished_logs()
        matching = [
            ld
            for ld in logs
            if "c1" in (ld.log_record.body or "") and "started" in (ld.log_record.body or "")
        ]
        assert len(matching) >= 1
        assert matching[0].log_record.severity_number == SeverityNumber.INFO
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_emits_error_log_record(monkeypatch):
    """AC2: invalid type POST /events → in-memory log exporter has a record with severity ERROR,
    body includes the invalid type value."""
    import psycopg
    from opentelemetry._logs import SeverityNumber

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    log_exporter = _InMemoryLogExporter()
    init_telemetry(log_exporter=log_exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400

        logs = log_exporter.get_finished_logs()
        matching = [ld for ld in logs if "frobnicated" in (ld.log_record.body or "")]
        assert len(matching) >= 1
        assert matching[0].log_record.severity_number.value >= SeverityNumber.ERROR.value
    finally:
        conn.close()
