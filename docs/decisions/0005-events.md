# 5. The service accepts five kinds of event

- **Date:** 2026-10-01
- **Status:** Accepted

## Context

A user sends the service what happens as it happens, and the metrics are computed from those events.

## Decision

The events are: started, blocked, unblocked, finished and escalated. The intake accepts exactly these.

## Consequences

A card that is blocked and then unblocked sends both. Blocked time is measured between them.

## Source

The service Goal and its decision D2 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)); mqucifer/crew#280 ([issue](https://github.com/mqucifer/crew/issues/280)).
