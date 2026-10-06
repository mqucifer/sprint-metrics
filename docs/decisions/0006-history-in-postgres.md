# 6. History is kept in Postgres, in the service's own schema

- **Date:** 2026-10-01
- **Status:** Accepted

## Context

The service keeps the history it is given across restarts and upgrades.

## Decision

The service keeps its history in Postgres, in its own schema, with its own user. It creates and migrates its schema at startup.

## Consequences

The service needs a Postgres client and a connection setting. Which server it uses in production is infra's (decision 0008).

## Source

The service Goal's decision D1 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)); the Sponsor's direction on mqucifer/crew#280 ([comment](https://github.com/mqucifer/crew/issues/280#issuecomment-5932484053)).
