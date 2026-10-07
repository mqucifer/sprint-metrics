# Changelog

## [Unreleased]

### Added

### Changed

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
