# Changelog

## [Unreleased]

### Added

- GET /range now names the window it is judging: a top-level `window` object carrying the sprint labels at both ends (`start`, `end`), the count of sprints in the window (`sprint_count`), and which sprints had no data (`no_data`), so a gap reads as 'no data' not zero. The response `api_version` moves from "4" to "5"
- GET /range carries each sprint's `dora` block with DORA's first two measures: `release_frequency` (how often epics ship, a whole count of distinct epics whose last story completes in the sprint) and `lead_time_days` (the mean, in whole days, of each released story's span from its creation to its epic's release moment); a sprint with events but no epic link reads both values as null (no data, not zero), and a sprint with no events reads the whole DORA block as null (#804, #807)

### Changed

### Fixed

- The SERVICE_ENDPOINTS description for GET /trend now lists `release_frequency` and `dora_lead_time_days` as valid metrics, matching the actual endpoint behaviour and docs/metrics.md

### Removed

## [4.1.0] - 2026-10-26

### Added

- The event intake (api_version stays "1") accepts an optional top-level `epic` string, an optional top-level `goal` string, and an optional `card.kind` string on every accepted event type; the three link fields are stored on every row that carries them (like points), absent fields store as NULL, and the resend rule (NULL fields fill in, set fields are not overwritten) applies to them as it does to points

- The 'returned' event type (a story handed back to the Business Analyst) is accepted at POST /events: it rides the common event fields and optionally carries failure_class (the reason for the send-back), failure_role (the step or role that sent the story back), and epic (the story's epic link); the three fields are stored on the returned row and are optional, and re-sending a returned event is as safe as re-sending any other event (#803)
- GET /range carries each sprint's `rework` answer: the stories sent back to the Business Analyst (its `returned` events), out of the stories started that sprint, each named by its identifier with the step it was sent back from and the reason in words; a send-back counts in the sprint of the `returned` event, a story sent back more than once is named once, and a sprint with no events (or no `returned` events) reads as no data, not zero (#803, #813)

- The rework answer on each sprint's `/range` entry is completed with the review/QA returns: `qa_returns` names the stories bounced at review or QA (its `attempt_failed` events), each by its identifier with the step it was returned from and the cause, using the same (failure class, returning role) values as `failure_breakdown`; a story that both went back to the Business Analyst and bounced at review appears in both parts, separately. `by_step` groups each part's returns by step (the count of rework per step), so the reader sees which step the sprint's rework concentrates in. The two parts are labeled and do not borrow each other's data (#803, #814)
- The finished event's cost payload accepts an optional `model_time_split` sub-object (refinement and delivery model seconds), validated under its own all-or-nothing rule and stored on the finished row, resend-safe
- GET /trend accepts the new `sent_backs_count` measure: the count of distinct stories sent back to the Business Analyst (its `returned` events) in the sprint; a sprint with events but no `returned` events reads null, not zero (#803)
- GET /range carries each sprint's `roster` naming, by identifier, the stories that completed in that sprint, the epics that released in that sprint (an epic releases in the sprint where its last story's finished event is), and the Goals that were achieved in that sprint (a Goal is achieved in the sprint where its last epic releases); sprints whose stories carry no epic or goal link read null for the corresponding roster part (no backfill), and sprints with no events read roster null (#804, #806)

### Changed

- The /range and /trend responses carry `api_version` "5"; version "4" is retired because /range's shape changed (the per-sprint roster). Event intake keeps `api_version` "1"

### Fixed

### Removed

## [4.0.0] - 2026-10-25

### Added

### Changed

- The /range and /trend responses carry `api_version` "4", the value that ships with the escalation removals; version "3" is retired. Event intake keeps `api_version` "1"

### Fixed

### Removed

- The escalation measures from GET /range: no sprint entry, `prior` or `delta` carries `escalation_rate_percent` or `escalation_count`, and the published range schema (`schemas/sprint-range.json`) no longer requires or describes them
- The escalation rate as a judged measure: it is no longer a default threshold (docs/thresholds.md drops its row), the range response's `flags` no longer carry `escalation_rate_percent`, and a thresholds override naming it produces no flag
- The escalation measures from GET /trend: asking for `escalation_rate_percent` or `escalation_count` now answers HTTP 400 saying the measure is no longer accepted; docs/metrics.md drops their rows and docs/service.md's valid-metrics list no longer names them
- The escalation measure code with its last consumer: `calculate_escalation_rate` (no longer re-exported by `sprint_metrics`) and the store's `count_escalated_events`; `metric_value` refuses both escalation names. docs/metrics.md drops its escalation boundary conditions and the README no longer lists the escalation rate. The `escalated` event type stays accepted and stored, unchanged

## [3.0.0] - 2026-10-25

### Added

### Changed

- The /range and /trend responses carry `api_version` "3"; version "2" is retired with the single-sprint answers this release removes. Event intake keeps `api_version` "1"

### Fixed

### Removed

- GET /metrics endpoint: the service no longer offers its stored metrics as Prometheus text; GET /range and GET /trend answer them, and the endpoint now returns HTTP 410. docs/metrics.md drops its Prometheus-name column
- The single-sprint response contract: `schemas/single-sprint.json`, the `SINGLE_SPRINT_SCHEMA` document, and the single-sprint JSON response formatter `format_json_report` (no longer re-exported by `sprint_metrics`), whose last consumer was the retired GET /sprint

## [2.0.0] - 2026-10-25

### Added

- The finished event accepts a cost payload on its card (`model_seconds`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, sent together or not at all), and the service stores it on the finished row (#713, #726)
- GET /range carries each sprint's `cost` (the cost middle and total) and `story_costs` (each finished story's cost); GET /trend and the service's GET /metrics carry the cost measures (#731, #733, #745); the generated docs describe them (#736)
- CI now validates CHANGELOG.md by rules that hold for every release: pyproject version matches the newest section, sections run newest-first by version with dates in order, [Unreleased] is first with standard subheadings, and every released heading is dated YYYY-MM-DD

### Changed

- GET /range's `top_failure_causes` is a list of `{"class", "role", "count"}` entries, empty as `[]`, where it was an object mapping cause to count, empty as `{}`; it and `failure_breakdown` count returns, one per return, by failure class and returning role, rather than failed stories (#734, #737)
- The /range and /trend responses carry `api_version` "2"; version "1" is retired because /range's shape changed. Event intake keeps `api_version` "1"

### Fixed

### Removed

- GET /sprint endpoint: single-sprint queries are answered by GET /range with a range spanning one sprint; the endpoint now returns HTTP 410
- The CLI-only doc pages: docs/usage.md, docs/cards.md, docs/formats.md, docs/scrape.md
- The `--thresholds` section from docs/thresholds.md; the README's install and usage stories retargeted to the released image; the service's startup example no longer takes `--service`
- The command-line report tool: the table, markdown, JSON and Prometheus report modes; the cards-file input (a path or stdin); the `--sprint-range`, `--prior-sprint` and `--prior` options; the threshold-file and metric-selection options `--thresholds`, `--metrics`, `--wip-limits`, `--escalations` and `--sprint-date`; and the `--service` flag, no longer needed because the image and the `sprint-metrics` command now start the service with no arguments and refuse any argument with a retirement message
- Scrape mode: the `--scrape` server (`sprint_metrics.serve`) with its `/metrics` and `/json` scrape endpoints, the Prometheus report formatter, and the cards-file and WIP-limits-file loaders it needed; the service's own `GET /metrics` still answers

## [1.3.3] - 2026-10-19

### Added

### Changed

### Fixed

- The single-sprint and sprint-range tables and the markdown standup report now flag every metric against the built-in default thresholds when no --thresholds file is given; a --thresholds file still overrides the defaults for the metrics it names, and the sprint-range markdown stays flag-free

### Removed

## [1.3.2] - 2026-10-19

### Added

### Changed

### Fixed

- The escalation rate is no longer capped at 100% (2 escalations on 1 completed card reports 200%), and the service's /metrics endpoint reports the stored per-sprint escalation rate instead of always 0

### Removed

## [1.3.1] - 2026-10-13

### Added

- docs/metrics.md, docs/cards.md, and docs/formats.md now describe `cycle_time_minutes`, `lead_time_minutes`, and the optional datetime card fields

### Changed

### Fixed

- `/sprint` and `/range` count `superseded` events in `superseded_count`, `superseded_points` and `superseded_breakdown`

### Removed

## [1.3.0] - 2026-10-13

### Added

- The `superseded` event type, stored with its reason and `replaced_by`
- Superseded count, points and per-reason breakdown in the CLI's single-sprint and range JSON and in the service's `/sprint` and `/range` responses, and accepted as `/trend` metric names
- The Superseded column in the single-sprint and range tables, and the superseded line in the markdown standup
- Superseded metric lines in the Prometheus exposition
- `cycle_time_minutes` and `lead_time_minutes` in the CLI's single-sprint and range JSON and in the service's `/sprint` and `/range` responses, and accepted as `/trend` metric names
- `card_created_at` stored on event intake

### Changed

- Superseded cards are left out of the in-progress and blocked counts

### Fixed

- `/sprint` finds a sprint whose name has a space
- The escalation rate has one definition and stays within 0 to 100
- `/range` accepts a range of one named sprint

### Removed

## [1.2.0] - 2026-10-10

### Added

- `/trend` query on the stateful service, and the trend response's JSON Schema
- OpenTelemetry from the service, configured by `OTEL_*` variables: a trace span for each HTTP request, and structured log records for service events
- The four JSON Schema files in `schemas/`, the CLI's JSON output and the event intake validated against them, and the README's version-tagged fetch
- The `attempt failed` event type, and the card's points accepted and stored
- Free-form sprint names in event intake and queries
- Points delivered, the first-attempt counts and the escalation count, in the CLI's JSON output and the service's `/sprint`, `/range` and `/trend` responses
- The full failure-breakdown list for each sprint in the `/range` response
- 503 from `POST /events` and from `GET /sprint`, `/range` and `/trend` when the database is unreachable
- POST /sprints endpoint to register sprint definitions (name, start_date, end_date, timezone) with upsert semantics
- docs/service.md: Automatic recovery section documenting that the service reconnects to its database automatically when the Postgres server restarts, with no container restart required

### Changed

- `/range` and `/trend` ordered by each sprint's start date
- Null metrics for a sprint with no stored events, in `/sprint`, `/range` and `/trend`, with the schemas allowing null

### Fixed

### Removed

## [1.1.0] - 2026-10-07

### Added

- Stateful service: board events over HTTP (started, blocked, unblocked, finished, escalated), sprint and range queries from Postgres, Prometheus /metrics endpoint, health-check endpoint, and event-intake JSON Schema at /schema/event
- Markdown health summary: `Changed:` line showing the metric with the largest absolute change when comparing to a prior sprint via `--prior-sprint`
- Markdown health summary: `Attention:` line showing blocked card count with longest block duration and in-progress card count
- Markdown standup report: indented detail line beneath the escalation-rate metric showing escalation count and completed-card count when the rate is non-zero

### Changed

### Fixed

### Removed

## [1.0.2] - 2025-07-15

### Added

### Changed

### Fixed

- Release mechanism: the release workflow now creates the version tag, GitHub Release, and container image independently, completing any missing artifacts on re-run

### Removed

## [1.0.1] - 2025-07-14

### Added

### Changed

### Fixed

- Release workflow: the release PR now correctly triggers publishing of the version tag, GitHub Release, and container image

### Removed

## [1.0.0] - 2025-07-13

### Added

- Sprint-metrics CLI: cycle time, lead time, throughput, WIP-limit violations,
  blocked-card aging, escalation rate, first-attempt rate, and failure breakdown

### Changed

### Fixed

### Removed
