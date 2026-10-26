# Stateful service

The stateful service accepts board events over HTTP and keeps their history in Postgres under its own schema. It answers range and trend queries from that history without the caller re-sending past data. The service is run from the released container image.

## Starting the service

The service reads its database connection string from the `SPRINT_METRICS_DB` environment variable. The Dockerfile sets no default; the variable must be provided at runtime. If `SPRINT_METRICS_DB` is not set or the database is unreachable at startup, the service exits with a non-zero code.

```
docker run -d -p 8080:8080 \
  -e SPRINT_METRICS_DB=postgresql://sprint:secret@db.internal:5432/sprint_metrics \
  ghcr.io/mqucifer/sprint-metrics:1.0.0
```

The service creates and migrates its schema at startup. It listens on port 8080 inside the container.

## Sprint registration

The service accepts sprint definitions via POST /sprints. Each sprint is registered by name before events that reference it are posted. The body carries the sprint's name, start date, end date, and timezone. If a sprint with the same name is already registered, its definition is updated in place.

## Event intake

The service accepts board events via POST /events. The accepted event types are: started, blocked, unblocked, finished, escalated, attempt_failed, superseded, and returned. A card's work counts in the sprint where it finishes, wherever it started. The `sprint` field accepts any non-empty string (e.g. 'Sprint 18', 'Q4-2026'); it is not restricted to calendar-month labels.

Every accepted event may carry three optional link fields, which the crew sends on any event type:

- `epic` (top-level, optional string): the story's epic link. Absent when the crew does not know the epic.
- `goal` (top-level, optional string): the story's goal link. Absent when the crew does not know the goal.
- `card.kind` (on the card object, optional string): the story's kind (for example 'story', 'epic', 'goal'). Absent when the crew does not know the kind.

When absent, the stored row holds no data (NULL) for the field. The intake version stays "1".

A `superseded` event marks a card that was replaced by other stories. It carries two fields beyond the common event fields:

- `because` (required): the reason the card was superseded. Accepts the values `"sponsor"` (at the Sponsor's request) or `"story_problem"` (after a story problem).
- `replaced_by` (optional): an array of story identifiers that replaced the card. Absent when the crew does not know the replacements.

No prior event on the card is required for a `superseded` event to be accepted.

A `returned` event marks a story that was handed back to the Business Analyst (for example, from review or QA back to refinement). Beyond the common event fields it carries three fields, all optional:

- `failure_role`: the step or role that sent the story back.
- `failure_class`: the reason the story was sent back.
- `epic`: the story's epic link.

No prior event on the card is required for a `returned` event to be accepted, and re-sending one is as safe as re-sending any other event.

Re-sending an event the service already holds (the same `card_id`, `type`, and `timestamp`) is safe. Fields that are currently NULL in the stored row receive the value supplied by the re-sent event; fields that already hold a value are not changed. You can replay your event log or upgrade your event payload without risking data corruption.

The intake format carries an `api_version` field. The current version is "1". The JSON Schema for the event body is available at GET /schema/event.

A `finished` event may carry a cost payload on its card object. The cost payload has five fields, each a non-negative integer, and the fields are sent together or not at all — a partial payload is rejected:

- `model_seconds` — total model time across every role's calls for this story
- `input_tokens` — total input tokens consumed
- `cached_input_tokens` — input tokens served from cache
- `output_tokens` — total output tokens produced
- `reasoning_output_tokens` — output tokens spent on reasoning

The cost payload may also carry an optional `model_time_split` sub-object that splits the story's model time between refinement and delivery. Its two fields are each a non-negative integer (model seconds), and the fields are sent together or not at all — a partial sub-object is rejected:

- `refinement` — model seconds spent in refinement
- `delivery` — model seconds spent in delivery

The `model_time_split` sub-object is independent of the five cost fields: a finished event may carry the split without the five fields, or the five fields without the split.

Example cost payload on a finished event's card:

```json
{
  "model_seconds": 3480,
  "input_tokens": 4000,
  "cached_input_tokens": 1800,
  "output_tokens": 900,
  "reasoning_output_tokens": 207,
  "model_time_split": {
    "refinement": 1200,
    "delivery": 2280
  }
}
```

## Endpoints

The service exposes the following HTTP endpoints: POST /sprints for sprint registration, POST /events for event intake, GET /range for multi-sprint queries, GET /trend for time-series queries, GET /schema/event for the event schema, and GET /health for liveness checks.

GET /range returns metrics for a range of sprints in chronological order. Each entry includes the prior-sprint delta. Its failure_breakdown and top_failure_causes count returns — one entry per return, by (failure class, returning role) — not one entry per failed story. Sprints with no events return all-null values.

The /range and /trend responses carry their own `api_version`, separate from the intake's: it is "4" from release 4.0.0. The value moves whenever what the responses offer changes. Version "3" (release 3.0.0) is retired: 4.0.0 removed the escalation measures (`escalation_rate_percent` and `escalation_count` are gone from /range and its flags, and /trend refuses them). Version "2" was retired in 3.0.0 with the single-sprint answers (GET /sprint and GET /metrics now answer 410), and version "1" in 2.0.0, when /range gained `cost` and `story_costs` and `top_failure_causes` became a list of `{class, role, count}` entries. Event intake keeps its own version, "1".

GET /trend answers the question 'what was this metric in each of these sprints?' by returning a value for every sprint label in the requested calendar range, with null for a sprint that has no events, so a gap reads as no data rather than zero. The range is specified by explicit start and end labels consistent with /range: `GET /trend?metric=throughput&start=2024-01&end=2024-04`.

### Error responses

When the database is unreachable, POST /events, GET /range, and GET /trend each return HTTP 503 with a JSON body identifying the condition as transient. The event or query was not processed; the client should retain the request and retry after a short delay. The 503 body is a JSON object containing an "error" field that names the database as the cause and a "retryable" field set to true, so the sender can safely retry without losing data.

When an internal service error occurs (not caused by the database), the service returns HTTP 500. The client should not retry a 500; it indicates a bug in the service and should be reported as an issue. The 500 body contains a description of the unexpected condition.

A request that fails validation (for example, a /range query whose start label is after its end label) returns HTTP 400 regardless of database state, because validation is performed before any database query is attempted. The client should not retry a 400.

GET /sprint returns HTTP 410 with a JSON body identifying the endpoint as removed. The endpoint is gone; a range spanning one sprint (GET /range) answers the same question. The 410 is distinct from a transient condition (503), a validation failure (400), and a service bug (500); the caller should switch to GET /range and not retry.

GET /metrics returns HTTP 410 with a JSON body identifying the endpoint as removed, with or without a query string and whether or not the database is reachable. The service no longer offers its stored metrics as Prometheus text; GET /range and GET /trend answer them.

BEGIN:service
Long-lived HTTP service that accepts board events and answers range and trend queries from Postgres.

| Method | Path | Description |
|---|---|---|
| POST | /sprints | Register or update a sprint definition (name, start date, end date, timezone). |
| POST | /events | Accept a board event (started, blocked, unblocked, finished, escalated, attempt_failed, superseded, returned). The service validates the card's created date and event type. |
| GET | /range | Return metrics for a range of sprints in chronological order. Each entry includes the prior-sprint delta. failure_breakdown and top_failure_causes count returns, one per return, by (failure class, returning role). Each entry also carries rework: the stories sent back to the Business Analyst (its returned events), out of the stories started that sprint; each sent-back story is named by its identifier, and each send-back carries the step it was sent back from and the reason. A send-back counts in the sprint of the returned event. Sprints with no events return all-null values, rework included. |
| GET | /trend | Return a single metric across a sprint range. Returns a JSON object with api_version and an ordered sequence of sprint-label-to-value pairs (the values array). Valid metrics: cycle_time_days, lead_time_days, throughput, wip_violations, blocked_aging_days, first_attempt_rate_percent, points_delivered, first_attempt_numerator, first_attempt_denominator, superseded_count, superseded_points, superseded_breakdown, cycle_time_minutes, lead_time_minutes, model_minutes_middle, model_minutes_total, input_tokens_middle, input_tokens_total, output_tokens_middle, output_tokens_total, cached_input_percent, reasoning_output_percent. Minute-based metrics (cycle_time_minutes, lead_time_minutes) return JSON integer values in minutes (rounded); sprints with no events return JSON null. |
| GET | /schema/event | Return the JSON Schema for the event intake body. |
| GET | /health | Health check. Returns 200 with {"status": "ok"} when the database is reachable, 503 otherwise. |
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
