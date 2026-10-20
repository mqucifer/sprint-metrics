# 11. Event name

- **Date:** 2026-10-20
- **Status:** Accepted

## Context

The Product Owner settled this for epic #684 (Report stories returned to the Business Analyst, replacing the escalation rate where there was no escalation), row R2, and it applies to every epic in the project. It's the Product Owner's own call, within the Goal (crew ADR 0018).

## Decision

The 8th accepted event is type 'returned' (a story handed back to the Business Analyst); amends the event vocabulary

## Consequences

VALID_EVENT_TYPES, the intake type enum, the board_events type CHECK and EVENT_INTAKE_SCHEMA gain 'returned'

## Source

Product Owner's call, within the Goal: "sprint-metrics decides how it takes these in and how it answers". Goal [mqucifer/sprint-metrics#666](https://github.com/mqucifer/sprint-metrics/issues/666) 'Each time a story goes back to the Business Analyst' + Decisions 9/10; epic #684's refinement conclusion, R2.

<!-- crew:from epic 684 R2 -->
