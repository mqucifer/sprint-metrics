# Telemetry

Part of the [service reference](../service.md).

The service emits its logs and traces as OpenTelemetry over OTLP. No custom collector is required.

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Sets the OTLP receiver URL | *(unset: telemetry disabled)* |
| `OTEL_SERVICE_NAME` | The service name reported in all spans and log records | `sprint-metrics` |

When `OTEL_EXPORTER_OTLP_ENDPOINT` is not set, all telemetry signals are dropped silently and the service is fully functional without an OTLP receiver.

## Sample span

Each HTTP request produces a span. The following shows the span emitted for a successful event intake, as it would appear in an APM:

```
Name:           POST /events
Service name:   sprint-metrics
Attributes:
  http.method       = "POST"
  http.route        = "/events"
  http.status_code  = 200
```

## Sample log record

Each accepted or rejected event produces a log record. The following shows the record emitted when an event is accepted:

```
Severity:   INFO
Body:       event accepted: card_id=c1 type=started
Attributes:
  card_id     = "c1"
  event_type  = "started"
```
