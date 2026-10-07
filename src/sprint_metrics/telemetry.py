"""OpenTelemetry configuration for the sprint-metrics service.

Reads OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_SERVICE_NAME from the environment
to configure the OTLP span and log exporters. When the endpoint is unset,
the SDK is left in its default no-op state.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

_DEFAULT_SERVICE_NAME = "sprint-metrics"

_tracer = None
_logger = None


def init_telemetry(span_exporter=None, log_exporter=None) -> None:
    """Initialize the OpenTelemetry SDK from OTEL_* environment variables.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_SERVICE_NAME from os.environ.
    When the endpoint is set, configures a TracerProvider with the service.name
    resource attribute and the given (or default OTLP) span exporter, and a
    LoggerProvider with the given (or default OTLP) log exporter.
    When the endpoint is unset, the SDK is left in its default no-op state.
    """
    global _tracer, _logger

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint is None:
        _tracer = trace.get_tracer("sprint-metrics")
        from opentelemetry._logs import get_logger

        _logger = get_logger("sprint-metrics")
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", _DEFAULT_SERVICE_NAME)
    resource = Resource({"service.name": service_name})

    provider = TracerProvider(resource=resource)
    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
    _tracer = provider.get_tracer("sprint-metrics")

    if log_exporter is not None:
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor

        log_provider = LoggerProvider(resource=resource)
        log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
        _logger = log_provider.get_logger("sprint-metrics")
    elif span_exporter is None:
        from opentelemetry.exporter.otlp.proto.grpc._log import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        log_provider = LoggerProvider(resource=resource)
        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint))
        )
        _logger = log_provider.get_logger("sprint-metrics")
    else:
        from opentelemetry._logs import get_logger

        _logger = get_logger("sprint-metrics")


def get_tracer():
    """Return the tracer instance created by init_telemetry."""
    if _tracer is None:
        init_telemetry()
    return _tracer


def get_logger():
    """Return the logger instance created by init_telemetry."""
    if _logger is None:
        init_telemetry()
    return _logger
