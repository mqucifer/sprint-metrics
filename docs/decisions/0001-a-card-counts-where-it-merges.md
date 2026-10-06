# 1. A card counts once, in the sprint it merges

- **Date:** 2026-09-30
- **Status:** Accepted

## Context

Sprint counting decides every per-sprint metric. A card's work can start in one sprint and finish in another.

## Decision

A card counts once, in the sprint where it merges. Merged is done, as the Definition of Done says.

## Consequences

Every per-sprint query groups a card by its merge date. A card isn't counted in the sprints it passed through.

## Source

The Sponsor's rule at sprint close, mqucifer/crew#389 ([issue](https://github.com/mqucifer/crew/issues/389)); the service Goal's decision D3 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)).
