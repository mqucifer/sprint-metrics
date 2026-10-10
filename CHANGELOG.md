# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

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
