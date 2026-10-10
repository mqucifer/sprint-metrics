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

## Sprint registration

The service accepts sprint definitions via POST /sprints. Each sprint is registered by name before events that reference it are posted. The body carries the sprint's name, start date, end date, and timezone. If a sprint with the same name is already registered, its definition is updated in place.

## Event intake

The service accepts board events via POST /events. The accepted event types are: started, blocked, unblocked, finished, escalated, and attempt_failed. A card's work counts in the sprint where it finishes, wherever it started. The `sprint` field accepts any non-empty string (e.g. 'Sprint 18', 'Q4-2026'); it is not restricted to calendar-month labels.

The intake format carries an `api_version` field. The current version is "1". The JSON Schema for the event body is available at GET /schema/event.

## Endpoints

The service exposes the following HTTP endpoints: POST /sprints for sprint registration, POST /events for event intake, GET /sprint for single-sprint queries, GET /range for multi-sprint queries, GET /trend for time-series queries, GET /metrics for Prometheus scraping, GET /schema/event for the event schema, and GET /health for liveness checks.

GET /trend answers the question 'what was this metric in each of these sprints?' by returning a value for every sprint label in the requested calendar range, defaulting to the metric's zero value when no events exist for that sprint. The range is specified by explicit start and end labels consistent with /range: `GET /trend?metric=throughput&start=2024-01&end=2024-04`.

### Error responses

When the database is unreachable, POST /events, GET /sprint, GET /range, and GET /trend each return HTTP 503 with a JSON body identifying the condition as transient. The event or query was not processed; the client should retain the request and retry after a short delay. The 503 body is a JSON object containing an "error" field that names the database as the cause and a "retryable" field set to true, so the sender can safely retry without losing data.

When an internal service error occurs (not caused by the database), the service returns HTTP 500. The client should not retry a 500; it indicates a bug in the service and should be reported as an issue. The 500 body contains a description of the unexpected condition.

A request that fails validation (for example, a /range query whose start label is after its end label) returns HTTP 400 regardless of database state, because validation is performed before any database query is attempted. The client should not retry a 400.

BEGIN:service
Long-lived HTTP service that accepts board events and answers sprint, range, and trend queries from Postgres.

| Method | Path | Description |
|---|---|---|
| POST | /sprints | Register a sprint definition (name, start_date, end_date, timezone) |
| POST | /events | Accept a board event (started, blocked, unblocked, finished, escalated, attempt_failed) |
| GET | /sprint | Query a single sprint's metrics |
| GET | /range | Query a range of sprints |
| GET | /trend | Return a time series for a single metric across an inclusive sprint range as a JSON object with api_version and an ordered sequence of sprint-label-to-value pairs (params: metric, start, end); sprints with no stored events return the metric's zero value. Metric names: cycle_time_days, lead_time_days, throughput, wip_violations, blocked_aging_days, escalation_rate_percent, first_attempt_rate_percent, failure_breakdown, points_delivered, first_attempt_numerator, first_attempt_denominator, escalation_count |
| GET | /metrics | Prometheus text exposition of stored history, sprint-labelled |
| GET | /schema/event | JSON Schema for the event intake format |
| GET | /health | Liveness/readiness check; 200 when the database is reachable |
END:service

## Automatic recovery

If the Postgres server restarts (for example, when Docker Desktop restarts), the service reconnects to its database automatically. No container restart is required for the service to resume answering requests.

While the database is unavailable, all query endpoints return HTTP 503. Once the database is reachable again, the endpoints resume returning HTTP 200 without any operator intervention.

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
