# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

## [4.4.1] - 2026-11-01

### Added

### Changed

- The /trend docs row now states the self-filed share measure's unit (a percent of the sprint's filed cards, the crew-filed count out of the total-filed count, the unknown cards included in the total), its precision (whole percent), its null and zero semantics, and where the per-sprint counts behind each value live (the per-sprint filed split in the /range answer)

### Fixed

- A sprint whose only stored rows are `filed` events now reads null for every delivery measure (rework, cost, DORA, working time, cost by kind, model time split, idle, roster) and appears in the window's `no_data`, as it did before `filed` rows existed. The `filed` answer is computed directly from the filed rows, independent of the delivery-event gate, so such a sprint still answers its filed split. In `/trend`, delivery measures read null for such a sprint while `self_filed_share_percent` keeps its value

### Removed

## [4.4.0] - 2026-11-01

### Added

- A new `/trend` measure, `self_filed_share_percent`: the whole percent of the sprint's total filed cards that the crew filed; null where the sprint carries no filing facts; registered in the measure registry with no better direction (movement only, like the cost measures)

### Changed

- The /range and /trend responses carry `api_version` "10"; version "9" is retired because /range's shape changed (the per-sprint `filed` answer) and /trend gained the `self_filed_share_percent` measure. Event intake keeps `api_version` "1"

- GET /trend's `self_filed_share_percent` and the per-sprint `/range` filed section read null, not a zero-count section, for a sprint that carries 'filed' events whose filing-fact fields are all absent (the filer, opener and project facts are never sent) — null means "no facts", distinct from a true zero, which is the answer for a sprint whose filing facts show the crew filed none of the sprint's cards. The `/trend` docs row states both answers and points to the `/range` filed section for the counts behind each value

### Fixed

### Removed

## [4.3.0] - 2026-11-01

### Added

- POST /events accepts a new ninth event type, `filed`, carrying the per-card filing facts (`filer`, `opener`, `project`) as optional string fields; the facts are stored as nullable columns on the card's `filed` event row with the existing fill-NULL resend semantics. A new `query_filed_events` store function returns a sprint's stored filing facts in event order
- A new `filed` section in each `/range` sprint entry: the sprint's filed-split answer (the crew-filed total broken into found, from-process, split and unknown, beside the Sponsor, operator and other counts, the sprint's total cards, and the self-filed share with its numerator and denominator); the answer is null when the sprint holds no filing facts, and the zero crew counts when the filing facts exist but the crew filed nothing
- docs/service.md's Event intake section documents the `filed` event's filing facts: the filer side values (`crew`, `sponsor`, `operator`, `other`), the opener kinds (`found`, `process`, `split`), unknown handling (the opener fact is left out when a card's opener cannot be told apart), card identity across projects (card ids are unique within a project; the `project` fact distinguishes cards with the same id in different repositories), a validating example event, and that the intake `api_version` stays "1"

### Changed

### Fixed

### Removed

## [4.2.1] - 2026-10-28

### Added

### Changed

- docs/service.md's generated /range section is laid out per measure: each /range answer (the window and its verdicts, the cost, the rework, the roster, DORA, the working time, the cost by kind, the model time split, and the idle time) is its own row in the endpoints table, each row's description coming from that answer's concern module's description fragment, so a new /range measure adds one fragment and one row rather than rewriting the other measures' text
- `SERVICE_ENDPOINTS`' /range description is composed from those per-measure fragments instead of a single hand-written string, and now carries the cost answer's fragment (previously omitted from the composed /range description); the model_time_split and idle description fragments and their attachment functions move from `sprint_metrics.service` to `sprint_metrics.time_splits`, and the standouts attachment function moves from `sprint_metrics.service` to `sprint_metrics.verdict`

### Fixed

### Removed

## [4.2.0] - 2026-10-28

### Added

- GET /range now names the window it is judging: a top-level `window` object carrying the sprint labels at both ends (`start`, `end`), the count of sprints in the window (`sprint_count`), and which sprints had no data (`no_data`), so a gap reads as 'no data' not zero. The response `api_version` moves from "4" to "5"
- GET /range carries each sprint's `dora` block with DORA's first two measures: `release_frequency` (how often epics ship, a whole count of distinct epics whose last story completes in the sprint) and `lead_time_days` (the mean, in whole days, of each released story's span from its creation to its epic's release moment); a sprint with events but no epic link reads both values as null (no data, not zero), and a sprint with no events reads the whole DORA block as null (#804, #807)
- GET /range carries DORA's change-failure rate and mean time to recovery per sprint: the `dora` block now also carries `change_failure_count` (the count of the sprint's releases that came back with rework, shown alongside its rate), `change_failure_rate_percent` (the whole percent of the sprint's releases that came back with rework, the change-failure rate), and `mean_time_to_recovery_minutes` (the mean, in whole minutes, of the completed recovery spans from the 'returned' event to the epic's next release moment); a sprint with releases but no rework reads count 0 and rate 0, a sprint with no releases or no epic link reads all three as null (no data, not zero) (#812, #813)
- GET /trend accepts the new `change_failure_count`, `change_failure_rate_percent`, and `mean_time_to_recovery_minutes` measures (#812, #813)
- A new verdict module (`sprint_metrics.verdict`) carries the measure registry — for every scalar measure the /range sprint entry carries, its better direction (lower, higher, or none), its unit, and its precision — and a verdict that judges a first value against a last purely from that (measure, better-direction) pair: measures with a better direction carry "better", "worse" or "flat", measures without one (the first-attempt counts and the cost measures) carry the movement "up", "down" or "flat"; a new measure plugs into the window verdict with only a registry entry (#802)
- GET /range carries each sprint's `working_time` answer: the minutes the crew's sessions ran, per step of a story's pipeline (a `returned` or `attempt_failed` row marks the step boundary; a rework session is labeled by the step it is reworking, the same step labels the rework answer uses), plus the sprint's working-time total; a blocked card's blocked interval is not counted, and a sprint with no events (or no closed session window) reads null, not zero (#805)
- GET /range carries each sprint's `cost_by_kind` answer: the sprint's working time split by story kind (addition and change), in whole minutes; a sprint whose stored story rows carry no kind reads null (no data, not zero), and a story whose kind is neither addition nor change contributes to neither (#805, #818)
- GET /trend accepts the new `working_time_minutes` measure: the sprint's working-time total in whole minutes, null for a sprint with no events or no closed session window (#805)
- GET /trend accepts the new `addition_working_time_minutes` and `change_working_time_minutes` measures: the sprint's working time for stories of the given kind in whole minutes, null where the sprint carries no kind data (#805, #818)
- The /range window object carries the window verdict: a `verdicts` object with one entry per registry measure, judging the window's first data-bearing sprint against its last — better, worse or flat, or up, down or flat for a measure with no better direction, against each measure's better direction — each entry naming both reference sprints and their values, with the unit and the precision; an entry reads null when the measure's value is missing in either reference sprint, or the window has fewer than two data-bearing sprints (a gap sprint is skipped, not read as zero; "flat" is the response's word for about the same) (#802)
- The /range window object carries the window's standouts: `biggest_improvement` (the measure, the two consecutive data-bearing sprints, the size of the step in the measure's own unit, and the unit and precision) and `worst_dip` (the same shape, for the largest adverse step), both computed only over measures with a better direction; a gap sprint is bridged, not read as zero, so 2024-01 to 2024-03 counts as one step when 2024-02 has no data. `turns` names the sprints where a measure turned — it moved one way from the previous data-bearing sprint and the other way into the next. `too_short` is true when the window has fewer than three data-bearing sprints, so a two-sprint result is not read as a trend (#802)
- GET /range carries each sprint's `model_time_split` answer: the sprint's model time split into refinement and delivery, in whole minutes (each story's split converted to whole minutes, the model_minutes display unit, and summed over the costed stories); a sprint whose costed stories carry the five-field cost payload but no split (the pre-Goal payloads), or a sprint with no costed stories at all, reads null (no data, not zero) (#805)
- GET /trend accepts the new `model_time_split_refinement_minutes` and `model_time_split_delivery_minutes` measures: the sprint's model time split into refinement and delivery, in whole minutes, null where no story in the sprint carries the split (#805)
- GET /range carries each sprint's `idle` answer: the idle time — the time that passed with no session running — against the sprint's total registered duration, in whole minutes. The span is the registered start date to the end of the registered end date, in the sprint's registered timezone, and each session window is clamped to the span (only the in-span part counts as session time); a rework session never re-sent as `started` reads as idle. A sprint with no events or no registered definition reads null, and where the sprint is registered but no session ran inside the span the duration is present and the idle time is null (the whole span is not reported as idle) (#805)
- GET /trend accepts the new `idle_minutes` measure: the sprint's idle time in whole minutes, null where the sprint is not registered or carries no session timestamps; the flat `idle_minutes` name also appears in each later sprint's `prior` and `delta` on /range (#805)

### Changed

- The /range and /trend responses carry `api_version` "9"; version "8" is retired because /range's shape changed (the per-sprint `idle` answer) and /trend gained the `idle_minutes` measure. Event intake keeps `api_version` "1"
- The /range cost answer (per-story cost list, cost middle/total, the six flat cost names, and the range attachment) moves from `sprint_metrics.service` to `sprint_metrics.metrics`, so cost work lands in the one module that owns the cost calculations
- The /range rework attachment (each range entry's rework object) and the rework answer's description fragment move from `sprint_metrics.service` to `sprint_metrics.rework`, so rework work lands in the one module that owns the rework calculation
- The /range dora attachment (each range entry's dora block) and the dora answer's description fragment move from `sprint_metrics.service` to `sprint_metrics.dora`, so DORA work lands in the one file that owns the DORA calculations
- The /range working_time attachment (each range entry's working_time object and its flat `working_time_minutes` name in prior/delta) and the /range cost_by_kind attachment (each range entry's cost_by_kind object and its flat `addition_working_time_minutes` and `change_working_time_minutes` names in prior/delta), along with their description fragments, move from `sprint_metrics.service` to `sprint_metrics.time_splits`, so working-time work lands in the one file that owns the working-time calculations
- The /range roster attachment (each range entry's roster object) and the roster answer's description fragment move from `sprint_metrics.service` to `sprint_metrics.store`, so roster work lands in the one file that owns the roster data query
- The /range window attachment (the top-level `window` object naming the window the response is judging: `start`, `end`, `sprint_count`, `no_data`) and the window answer's description fragment move from `sprint_metrics.service` to `sprint_metrics.sprint_range`, so window work lands in the one module that owns the range base formatter
- The /range verdict attachment (the window object's `verdicts` object with one entry per registry measure, judging the flat values of each range entry against the measure registry) and the verdict answer's description fragment move from `sprint_metrics.service` to `sprint_metrics.verdict`, so verdict work lands in the one file that owns the measure registry and the window verdict

### Fixed

- The SERVICE_ENDPOINTS description for GET /trend now lists `release_frequency` and `dora_lead_time_days` as valid metrics, matching the actual endpoint behaviour and docs/metrics.md
- The GET /trend row in docs/service.md now states DORA's four measures' units — `release_frequency` in releases per sprint, `dora_lead_time_days` in whole days, `change_failure_rate_percent` in whole percent (shown alongside its `change_failure_count`), and `mean_time_to_recovery_minutes` in whole minutes — and states that a sprint without a derivable DORA value (no events, or no epic link, or no epic release for the change-failure and recovery measures) returns JSON null

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
