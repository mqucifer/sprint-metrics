# Stateful service

The stateful service accepts board events over HTTP and keeps their history in Postgres under its own schema. It answers sprint, range, and trend queries from that history without the caller re-sending past data. The service is run from the released container image.

## Starting the service

The service reads its database connection string from the `SPRINT_METRICS_DB` environment variable. The Dockerfile sets no default; the variable must be provided at runtime. If `SPRINT_METRICS_DB` is not set or the database is unreachable at startup, the service exits with a non-zero code.

```
docker run -d -p 8080:8080 \
  -e SPRINT_METRICS_DB=postgresql://sprint:secret@db.internal:5432/sprint_metrics \
  ghcr.io/mqucifer/sprint-metrics:1.0.0 --service
```

The service creates and migrates its schema at startup. It listens on port 8080 inside the container.

## Event intake

The service accepts board events via POST /events. The accepted event types are: started, blocked, unblocked, finished, and escalated. A card's work counts in the sprint where it finishes, wherever it started.

The intake format carries an `api_version` field. The current version is "1". The JSON Schema for the event body is available at GET /schema/event.

## Endpoints

The service exposes the following HTTP endpoints: POST /events for event intake, GET /sprint for single-sprint queries, GET /range for multi-sprint queries, GET /metrics for Prometheus scraping, GET /schema/event for the event schema, and GET /health for liveness checks.

BEGIN:service
Long-lived HTTP service that accepts board events and answers sprint, range, and trend queries from Postgres.

| Method | Path | Description |
|---|---|---|
| POST | /events | Accept a board event (started, blocked, unblocked, finished, escalated) |
| GET | /sprint | Query a single sprint's metrics |
| GET | /range | Query a range of sprints |
| GET | /trend | Query a single metric's value across an inclusive sprint range |
| GET | /metrics | Prometheus text exposition of stored history, sprint-labelled |
| GET | /schema/event | JSON Schema for the event intake format |
| GET | /health | Liveness/readiness check; 200 when the database is reachable |
END:service

## Telemetry

The service emits its logs and traces as OpenTelemetry over OTLP. No custom collector is required.

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Sets the OTLP receiver URL | *(unset: telemetry disabled)* |
| `OTEL_SERVICE_NAME` | The service name reported in all spans and log records | `sprint-metrics` |

When `OTEL_EXPORTER_OTLP_ENDPOINT` is not set, all telemetry signals are dropped silently and the service is fully functional without an OTLP receiver.

### Sample span

Each HTTP request produces a span. The following shows the span emitted for a successful event intake, as it would appear in an APM:

```
Name:           POST /events
Service name:   sprint-metrics
Attributes:
  http.method       = "POST"
  http.route        = "/events"
  http.status_code  = 200
```

### Sample log record

Each accepted or rejected event produces a log record. The following shows the record emitted when an event is accepted:

```
Severity:   INFO
Body:       event accepted: card_id=c1 type=started
Attributes:
  card_id     = "c1"
  event_type  = "started"
```
