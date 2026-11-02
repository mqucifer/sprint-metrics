# 13. Session event

- **Date:** 2026-11-02
- **Status:** Accepted

## Context

The Product Owner settled this for epic #939 (Record the crew's sessions as what happened), row R1, and it applies to every epic in the project.

## Decision

'session' is the 10th accepted event type on POST /events; amends the event vocabulary

## Consequences

VALID_EVENT_TYPES, the intake type enum, and EVENT_INTAKE_SCHEMA gain 'session'; card_id and card are optional at the envelope level for a session; the sessions table holds each session idempotently on its natural identity

## Source

Goal [mqucifer/sprint-metrics#939](https://github.com/mqucifer/sprint-metrics/issues/939) + Decisions 9, 10 and 12; epic #939's refinement conclusion, R1.

<!-- crew:from epic 939 R1 -->
