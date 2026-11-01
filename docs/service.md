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

The service accepts board events via POST /events. The accepted event types are: started, blocked, unblocked, finished, escalated, attempt_failed, superseded, returned, and filed. A card's work counts in the sprint where it finishes, wherever it started. The `sprint` field accepts any non-empty string (e.g. 'Sprint 18', 'Q4-2026'); it is not restricted to calendar-month labels.

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

A `filed` event reports the per-card filing facts: who filed the card, what opened it, and — for a card filed in another repository, such as a QA Task filed in qa-suite — the project the card is for and counts for. Each is a fact the crew sends, not a count, and each is optional:

- `filer` (top-level, optional string): who filed the card. The crew sends one of the filer-side values: `"crew"` (the crew that builds the service), `"sponsor"` (the Sponsor), `"operator"` (the operator), or `"other"` (anyone else). Absent when the crew does not know who filed the card (in `other`).
- `opener` (top-level, optional string): what opened the card. The crew sends one of the opener kinds: `"found"` (a role found a problem), `"process"` (the crew's own test, release, review, technical epic, or retro), or `"split"` (a split from something already filed). Absent when the card's opener cannot be told apart — the card is then reported as unknown.
- `project` (top-level, optional string): for a card filed in another repository, the project the card is for and counts for (for example `"qa-suite"`). Absent when the card was filed in the same repository as the sprint, or when the crew does not know the project.

When the opener fact is absent, the card is reported as unknown: the opener fact is left out rather than guessed, and the service never infers a bucket from an absent fact.

Card ids are unique within a project. The `project` fact is what tells a card `"123"` filed in one repository apart from the card `"123"` filed in another: the two count as two distinct cards.

Example `filed` event carrying the filing facts:

```json
{
  "api_version": "1",
  "card_id": "42",
  "type": "filed",
  "timestamp": "2024-03-05T09:00:00Z",
  "sprint": "2024-03",
  "card": {
    "created": "2024-03-04"
  },
  "filer": "crew",
  "opener": "process",
  "project": "qa-suite"
}
```

The intake's `api_version` stays "1": the `filed` event is additive. Events without the filing facts are accepted exactly as today, so nothing already sent stops working.

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

GET /range returns metrics for a range of sprints in chronological order. Each entry includes the prior-sprint delta. Its failure_breakdown and top_failure_causes count returns — one entry per return, by (failure class, returning role) — not one entry per failed story. Sprints with no events return all-null values. The response carries a top-level `window` object naming the window it is judging: `start` (the first sprint label), `end` (the last sprint label), `sprint_count` (the number of sprints in the window), and `no_data` (the sprint labels that had no events). The window object also carries a `verdicts` object with one entry per registry measure: each entry judges the window's first and last data-bearing sprint — a sprint with no events is skipped, not read as zero — against that measure's better direction, reading better, worse or flat, and (for a measure with no better direction, such as the cost measures) up, down or flat. Each entry names both reference sprints and their values, with the measure's unit and precision. An entry reads null when the measure's value is missing in either reference sprint, or the window has fewer than two data-bearing sprints: a measure with a missing number gets no verdict, not a zero. "Flat" is the response's word for about the same: the measure's value is equal in both reference sprints. The window object also names the standouts: `biggest_improvement` (the measure, the two consecutive data-bearing sprints, the size of the step in the measure's own unit, and the unit and precision — null when the window has fewer than two data-bearing sprints), `worst_dip` (the same shape, for the largest adverse step), and `turns` (a list of the sprints where a measure turned: it moved one way from the previous data-bearing sprint and the other way into the next — a measure with a flat step in between does not turn). A gap sprint is bridged, not read as zero: the step from the data-bearing sprint before the gap to the one after is one step. `too_short` is true when the window has fewer than three data-bearing sprints, so a two-sprint result is not read as a trend. Each entry also carries a `roster` naming, by identifier, the stories that completed in that sprint, the epics that released in that sprint (an epic releases in the sprint where its last story's finished event is), and the Goals that were achieved in that sprint (a Goal is achieved in the sprint where its last epic releases). Sprints whose stories carry no epic or goal link read null for the corresponding roster part (no backfill).

The /range and /trend responses carry their own `api_version`, separate from the intake's: it is "10" from release 10.0.0. The value moves whenever what the responses offer changes. Version "9" is retired: 10.0.0 adds each sprint's filed answer to /range (the filed-split answer — the total the crew filed, of which found by a role, from its own process, and split from already-filed work, beside what the Sponsor, the operator and anyone else filed; cards that can't be told apart reported as unknown, never guessed) and the `self_filed_share_percent` measure to /trend (the whole percent of the sprint's total filed cards that the crew filed, null where the sprint carries no filing facts). Version "8" is retired: 9.0.0 adds each sprint's idle answer to /range (the idle time — the time that passed with no session running — against the sprint's total registered duration, in whole minutes) and the `idle_minutes` measure to /trend. Version "7" is retired: 8.0.0 adds each sprint's model-time split answer to /range (the sprint's model time split into refinement and delivery, in whole minutes) and the `model_time_split_refinement_minutes` and `model_time_split_delivery_minutes` measures to /trend. Version "6" is retired: 7.0.0 adds each sprint's cost-by-kind answer to /range (the sprint's working time split by story kind — addition and change — in whole minutes) and the `addition_working_time_minutes` and `change_working_time_minutes` measures to /trend. Version "5" is retired: 6.0.0 adds each sprint's working-time answer to /range (the minutes the crew's sessions ran, per step of a story's pipeline, plus the sprint's working-time total) and the `working_time_minutes` measure to /trend. Version "4" is retired: 5.0.0 adds the per-sprint roster (completed stories, released epics, achieved Goals by identifier) to /range and names the window the response is judging (a top-level `window` object carrying the sprint labels at both ends, the sprint count, and which sprints had no data). Version "3" (release 3.0.0) is retired: 4.0.0 removed the escalation measures (`escalation_rate_percent` and `escalation_count` are gone from /range and its flags, and /trend refuses them). Version "2" was retired in 3.0.0 with the single-sprint answers (GET /sprint and GET /metrics now answer 410), and version "1" in 2.0.0, when /range gained `cost` and `story_costs` and `top_failure_causes` became a list of `{class, role, count}` entries. Event intake keeps its own version, "1".

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
| POST | /events | Accept a board event (started, blocked, unblocked, finished, escalated, attempt_failed, superseded, returned, filed). The service validates the card's created date and event type. |
| GET | /range | Return metrics for a range of sprints in chronological order. Each entry includes the prior-sprint delta. failure_breakdown and top_failure_causes count returns, one per return, by (failure class, returning role). |
| GET | /range | The response carries a top-level window object naming the window it is judging: start (the first sprint label), end (the last sprint label), sprint_count (the number of sprints in the window), and no_data (the sprint labels that had no events). |
| GET | /range | The response also carries a verdicts object with one entry per registry measure: it judges the window's first and last data-bearing sprint (a gap sprint is skipped, not read as zero) against each measure's better direction — better, worse or flat, or up, down or flat for a measure with no better direction — each entry naming both reference sprints and their values, with the unit and the precision; an entry reads null when the measure's value is missing in either reference sprint, or the window has fewer than two data-bearing sprints. |
| GET | /range | Each entry also carries a cost answer: the per-story cost list (story_costs, each costed story's model minutes, input and output tokens, and the sprint's combined cached-input and reasoning-output percents) and the sprint's cost middle and total (the median and sum of the three measures across costed stories). The six flat cost names (model_minutes_middle, model_minutes_total, input_tokens_middle, input_tokens_total, output_tokens_middle, output_tokens_total) appear on each entry's prior and delta. A sprint with no costed stories reads null for cost, not zero. |
| GET | /range | Each entry also carries rework: two labeled parts — sent_backs (the stories sent back to the Business Analyst, its returned events, out of the stories started that sprint; each sent-back story is named by its identifier, and each send-back carries the step it was sent back from and the reason) and qa_returns (the review/QA returns, using the same (failure class, returning role) values as failure_breakdown; each returned story is named by its identifier, and each return carries the step it was returned from and the cause). A send-back counts in the sprint of the returned event. by_step groups each part's returns by step. Sprints with no events return all-null values, rework included. |
| GET | /range | Each entry also carries filed: the sprint's filed-split answer — the total the crew filed (crew_total), of which found by a role (found), from its own process (from_process), and split from already-filed work (split), beside what the Sponsor (sponsor), the operator (operator), and anyone else or cards with no known filer (other) filed; cards that can't be told apart are reported as unknown, never guessed. total_cards is the sprint's total filed cards; the buckets partition the sprint (crew_total = found + from_process + split + unknown, and crew_total + sponsor + operator + other = total_cards). self_filed_share carries the whole percent of the sprint's total cards that the crew filed, with its numerator (crew_total) and denominator (total_cards). A card counts in the sprint named on its 'filed' event (the sprint it was filed in), which may differ from the sprint where it merges. The filed answer is computed from the sprint's filed rows, independent of its delivery events: a sprint whose only stored rows are filed reads null for every delivery measure but still answers its filed split. A sprint with events but no filing facts reads filed null (no data, not zero); a sprint with filing facts in which the crew filed nothing reads the zero crew counts. |
| GET | /range | Each entry also carries a roster naming, by identifier, the stories that completed in that sprint, the epics that released in that sprint (an epic releases in the sprint where its last story's finished event is), and the Goals that were achieved in that sprint (a Goal is achieved in the sprint where its last epic releases). Sprints whose stories carry no epic or goal link read null for the corresponding roster part (no backfill). |
| GET | /range | Each entry also carries a dora block: the sprint's release frequency (how often epics actually ship) and lead time for changes (the mean, in whole days, of each released story's span from its creation to its epic's release moment); a sprint whose finished events carry no epic link reads null for both, not zero. |
| GET | /range | Each entry also carries a working_time answer: the minutes the crew's sessions ran, per step of a story's pipeline (a returned or attempt_failed row marks the step boundary; a rework session is labeled by the step it is reworking), plus the sprint's working-time total; a sprint with no events (or no closed session window) reads null. |
| GET | /range | Each entry also carries a cost_by_kind answer: the sprint's working time split by story kind (addition and change), in whole minutes; a sprint whose stored story rows carry no kind reads null (no data, not zero). |
| GET | /range | Each entry also carries a model_time_split answer: the sprint's model time split into refinement and delivery, in whole minutes (each story's split converted to whole minutes and summed over the costed stories); a sprint whose stories carry no model-time split (or no costed stories at all) reads null (no data, not zero). |
| GET | /range | Each entry also carries an idle answer: the sprint's idle time — the time that passed with no session running — against the sprint's total registered duration, in whole minutes (a session window clamped to the registered span; a rework session never re-sent as started reads as idle); a sprint with no events or no registered definition reads null. |
| GET | /trend | Return a single metric across a sprint range. Returns a JSON object with api_version and an ordered sequence of sprint-label-to-value pairs (the values array). Valid metrics: cycle_time_days, lead_time_days, throughput, wip_violations, blocked_aging_days, first_attempt_rate_percent, points_delivered, first_attempt_numerator, first_attempt_denominator, superseded_count, superseded_points, superseded_breakdown, cycle_time_minutes, lead_time_minutes, model_minutes_middle, model_minutes_total, input_tokens_middle, input_tokens_total, output_tokens_middle, output_tokens_total, cached_input_percent, reasoning_output_percent, sent_backs_count, release_frequency, dora_lead_time_days, change_failure_count, change_failure_rate_percent, mean_time_to_recovery_minutes, working_time_minutes, addition_working_time_minutes, change_working_time_minutes, model_time_split_refinement_minutes, model_time_split_delivery_minutes, idle_minutes, self_filed_share_percent. Minute-based metrics (cycle_time_minutes, lead_time_minutes) return JSON integer values in minutes (rounded); sprints with no events return JSON null. working_time_minutes returns the sprint's working-time total in whole minutes (null where the sprint has no closed session window). addition_working_time_minutes and change_working_time_minutes return the sprint's working time for stories of the given kind in whole minutes (null where the sprint carries no kind data). model_time_split_refinement_minutes and model_time_split_delivery_minutes return the sprint's model time split into refinement and delivery, in whole minutes (null where no story in the sprint carries a split). release_frequency returns the sprint's count of distinct epics released, in releases per sprint. dora_lead_time_days returns the mean lead time for changes, in whole days. change_failure_count and change_failure_rate_percent return the sprint's change-failure rate in whole percent (the rate is shown alongside its count). mean_time_to_recovery_minutes returns the mean time to recovery, in whole minutes. A sprint without a derivable DORA value (no events, or no epic link, or no epic release for the change-failure and recovery measures) returns JSON null. idle_minutes returns the sprint's idle time — the time that passed with no session running against the sprint's total registered duration — in whole minutes (null where the sprint is not registered or carries no session timestamps). self_filed_share_percent returns the whole percent of the sprint's filed cards that the crew filed itself. Its unit is a percent of the sprint's filed cards: the crew-filed count out of the total-filed count, the unknown cards included in the total. The counts behind each value live in the sprint's per-sprint filed split in the /range answer (the total the crew filed, of which found, from its own process, and split from something already filed, beside the Sponsor's, the operator's and anyone else's filings, and the unknown cards). A card counts in the sprint it was filed in, not the sprint it merged. A null value means the sprint holds no filing facts (no data — the service never answers 0 or 100 for a fact-less sprint, and null is not 'no self-filed work'); a 0 is a different, true answer: the sprint's stored facts show the crew filed none of the cards filed in that sprint. |
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
