# Architecture

The system as the code has it (2026-10-25, 4.0.0), drawn as a C4 diagram in
Mermaid: context, containers, and components. This file is the repository's
diagram of record: each Goal's target diagram is drawn from it, and becomes it
once the Goal is done (ADR 0036). Update it when the code changes.

## Context

The crew is the only user. Nobody uses sprint-metrics directly: the crew runs
its image, sends it sprint definitions and board events, and reads its answers
back. The Sponsor sees its results second-hand, on the crew-presentation site.

```mermaid
C4Context
    title sprint-metrics — Context
    Person(crew, "The Crew", "Runs the container image, sends sprint definitions and board events, and reads sprint ranges and trends back.")
    System(sprintMetrics, "sprint-metrics", "Delivery metrics for the crew's board: a stateful event service in one Python package.")
    SystemDb(postgres, "Postgres", "A shared server; sprint-metrics keeps its history in its own schema, sprint_metrics.")
    System(otlp, "OTLP receiver", "Optional; receives the service's logs and traces when OTEL_EXPORTER_OTLP_ENDPOINT is set.")
    System(gh, "GitHub", "Version tags vX.Y.Z, GitHub Releases, and the container image at ghcr.io/mqucifer/sprint-metrics.")

    Rel(crew, sprintMetrics, "runs the image", "docker")
    Rel(crew, sprintMetrics, "sends sprints and board events; queries ranges and trends", "HTTP")
    Rel(sprintMetrics, postgres, "persists board events and sprint definitions; answers queries from them", "psycopg, SPRINT_METRICS_DB")
    Rel(sprintMetrics, otlp, "emits logs and traces when configured", "OTLP")
    Rel(crew, gh, "pulls the image by its tag")
```

## Containers

The package is one Python 3.12 service. It is released as a git tag and as a
container image at `ghcr.io/mqucifer/sprint-metrics`. The image's entrypoint is
the `sprint-metrics` command, which starts the service with no arguments and
refuses any argument: the command-line report tool and its scrape server were
retired in 2.0.0.

```mermaid
C4Container
    title sprint-metrics — Containers
    Person(crew, "The Crew")
    SystemDb(postgres, "Postgres", "Shared server. Owns the sprint_metrics schema: board_events (keyed by card_id, type, event_time) and sprints.")
    System(otlp, "OTLP receiver", "Optional.")

    Boundary(boundary, "sprint-metrics", "Python 3.12 package, src/sprint_metrics; released at a tag and as a container image") {
        Container(service, "Stateful service", "sprint_metrics.service", "Long-lived HTTP server on port 8080: POST /sprints and /events; GET /range, /trend, /schema/event, /schema/trend, /health; GET /sprint and GET /metrics answer 410. Requires a database.")
    }

    Rel(crew, service, "POSTs board events and sprint definitions; GETs queries", "HTTP")
    Rel(service, postgres, "upserts events, queries from them; reconnects if the server restarts", "psycopg")
    Rel(service, otlp, "logs and traces, one span per request", "OTLP")
```

## Components

The package is divided by concern so that parallel stories land in different
files. Only the service touches the database, and all SQL lives in `store.py`.

```mermaid
C4Component
    title sprint-metrics — Components
    Boundary(pkg, "sprint_metrics package") {
        Component(svc, "service.py", "Stateful HTTP service and the entry point (main) of the sprint-metrics script and python -m: event intake, sprint registration, range and trend queries, and /health.")
        Component(card, "card.py", "Card dataclass and card parsing.")
        Component(metrics, "metrics.py", "Pure metric calculations: cycle time, lead time, throughput, WIP violations, blocked aging, first-attempt rate, failure breakdown and its top causes, cost metrics.")
        Component(thresholds, "thresholds.py", "Built-in default thresholds and flag calculation.")
        Component(report, "report.py", "API_VERSION and the metric display names.")
        Component(sr, "sprint_range.py", "Sprint-label parsing and the per-sprint range JSON.")
        Component(schema, "schema.py", "JSON Schema documents for the API: sprint-range, trend, and event intake.")
        Component(store, "store.py", "Postgres persistence: the sprint_metrics schema DDL, idempotent event upsert, and the query functions. All SQL lives here.")
        Component(otel, "telemetry.py", "OpenTelemetry setup: tracer, logger, OTLP exporter, from OTEL_* environment variables.")
        Component(docgen, "_docs_gen.py", "Dev tool, not part of the public API: regenerates the marked (generated) sections of the docs/ files from the code.")
    }
    ContainerDb(db, "Postgres", "sprint_metrics schema: board_events, sprints.")

    Rel(svc, metrics, "computes metrics from reconstructed cards")
    Rel(svc, report, "API_VERSION")
    Rel(svc, sr, "range parsing and range JSON")
    Rel(svc, schema, "event-intake and trend schemas")
    Rel(svc, store, "upserts events, answers queries")
    Rel(svc, otel, "tracer and logger per request")
    Rel(sr, thresholds, "flags against the defaults")
    Rel(store, card, "reconstructs Card objects from stored rows")
    Rel(store, db, "all SQL")
    Rel(docgen, metrics, "reads the calculate_* docstrings and ALL_METRICS")
    Rel(docgen, report, "reads _METRIC_COLUMNS")
    Rel(docgen, thresholds, "reads DEFAULT_THRESHOLDS")
    Rel(docgen, schema, "reads the schema documents")
    Rel(docgen, svc, "reads SERVICE_ENDPOINTS")
```

## Notes

- **The service is the only mode, and it requires Postgres.** It exits
  non-zero at startup if `SPRINT_METRICS_DB` is unset or the database is
  unreachable.
- **History lives in Postgres, under the service's own schema.**
  `sprint_metrics.board_events` is keyed by `(card_id, type, event_time)`, so
  re-sending an event is safe; `sprint_metrics.sprints` holds the sprint
  definitions registered via POST /sprints. The service never constructs
  queries outside `store.py`.
- **The event intake and the query responses are contracted by JSON Schema.**
  The schemas are published in `schemas/` at each release tag and served by
  the service at GET /schema/event; the response `api_version` is independent
  of the package version.
- **Telemetry is optional and service-only.** With
  `OTEL_EXPORTER_OTLP_ENDPOINT` unset the SDK stays a no-op and the service is
  fully functional.
- **A release is a published version.** A tag `vX.Y.Z` on this repository, a
  GitHub Release, and a container image at
  `ghcr.io/mqucifer/sprint-metrics:X.Y.Z` (plus `X.Y` and `latest`); see
  ADR 0002 and 0003 in [docs/decisions](decisions/).
- **`_docs_gen.py` is a dev tool.** It keeps the marked sections of
  `docs/metrics.md`, `docs/thresholds.md`, and `docs/service.md` in step with
  the code, and rewrites the three JSON Schema files in `schemas/`; it takes
  no part in the running service.
- **GET /trend is built but unused today.** Comparing sprints across a range
  is what this project is for, so the endpoint is to be made good, not
  retired.

User-facing documentation lives in [README](../README.md) and
[docs/](metrics.md); decisions that apply to every Goal live in
[docs/decisions/](decisions/README.md).
