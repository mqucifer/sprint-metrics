"""Tests for OpenTelemetry configuration in sprint_metrics.telemetry."""

from __future__ import annotations


def test_init_telemetry_uses_service_name_from_env(monkeypatch):
    """AC1: endpoint and service name set → span resource carries service.name='sprint-metrics'."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from sprint_metrics.telemetry import get_tracer, init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "sprint-metrics")

    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    tracer = get_tracer()
    with tracer.start_as_current_span("test"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].resource.attributes["service.name"] == "sprint-metrics"


def test_init_telemetry_defaults_service_name(monkeypatch):
    """AC2: endpoint set but OTEL_SERVICE_NAME absent → default service.name='sprint-metrics'."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from sprint_metrics.telemetry import get_tracer, init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    tracer = get_tracer()
    with tracer.start_as_current_span("test"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].resource.attributes["service.name"] == "sprint-metrics"
