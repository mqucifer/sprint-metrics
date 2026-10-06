# 8. The service builds to its runtime contract; infra runs it

- **Date:** 2026-10-05
- **Status:** Accepted

## Context

Proving the service in CI and running it in production are different jobs (crew ADR 0017).

## Decision

sprint-metrics builds to its spec and proves it in CI. Its runtime contract is: it reads its settings from the environment (`SPRINT_METRICS_DB`, and the `OTEL_*` settings for telemetry); it creates its schema at startup; and CI proves it against a throwaway Postgres with no real secrets. Where it runs in production, the production database and its secrets are infra's.

## Consequences

Stories prove the contract in CI. A need of the deployed runtime goes to infra, not into a story.

## Source

Crew ADR 0017 ([decision](https://github.com/mqucifer/crew/blob/main/docs/decisions/0017-the-product-builds-to-its-spec-infra-owns-where-it-runs.md)); the service Goal's decisions D7 and D8 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)).
