# 4. Everything is provable on a pull request

- **Date:** 2026-09-28
- **Status:** Accepted

## Context

Some criteria, such as an image build or a workflow, can only run in CI.

## Decision

Everything is provable on a pull request. Docker runs in CI only, never as a local requirement, and a criterion only CI can prove names the check that runs it.

## Consequences

A story's criteria are proven before it merges. A criterion no check runs is unproven.

## Source

mqucifer/sprint-metrics#186 ([issue](https://github.com/mqucifer/sprint-metrics/issues/186)); the service Goal's decision D6 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)).
