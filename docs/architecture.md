# Architecture

The system as built (2026-10-25, 4.0.0): Goal mqucifer/sprint-metrics#749's
target diagram, corrected to what the code shows. This file is the
repository's diagram of record: each Goal's target diagram is drawn from it,
and becomes it once the Goal is done (ADR 0036). Update it when the code
changes.

```mermaid
C4Container
    title sprint-metrics, as the repository has it, with the Goal's (mqucifer/sprint-metrics#749) retirements and new parts
    Person(crew, "The crew", "Every tick: sends sprints and events, reads one sprint range back")
    System(site, "Crew-presentation site", "The Sponsor's sprint overview, built from that range")
    System(otel, "Observability backend", "Ingests the service's OpenTelemetry logs and traces over OTLP")
    System(pg, "Shared Postgres server", "Holds the service's own sprint_metrics schema and user")
    Boundary(img, "sprint-metrics container image") {
        Container(entry, "Image entry point: the service, no arguments (new in #751)", "Runs the service with no flags. The CLI report tool (cards file in, table/markdown/JSON/Prometheus out, threshold and metric-selection options, --scrape server) is retired; no command-line report tool remains (mqucifer/sprint-metrics#751)", "Python 3.12")
        Container(service, "HTTP service", "POST /sprints, POST /events, GET /range, GET /trend, GET /health, GET /schema/event, GET /schema/trend. GET /sprint (410 since 2.0.0, story #768) and the custom Prometheus GET /metrics (410 since 3.0.0, mqucifer/sprint-metrics#752) are retired")
        Container(measures, "Measures and flags", "Pure metric calculations, thresholds, flags. The escalation measures are removed (mqucifer/sprint-metrics#753); the 'escalated' event stays accepted and stored")
        Container(store, "Postgres store", "Schema DDL, idempotent event upsert, sprint/range/trend queries; all SQL lives here")
        Container(contract, "Published contract", "api_version (new value per response change: 2 at 2.0.0, 3 at 3.0.0, 4 at 4.0.0 after mqucifer/sprint-metrics#753; event intake keeps 1), JSON schemas in schemas/ pinned per tag, docs")
    }
    Rel(crew, entry, "Runs the image by tag; tick = POST /sprints, POST /events, GET /range", "HTTP")
    Rel(site, service, "The sprint range the overview is built from", "HTTP")
    Rel(entry, service, "Starts the service process")
    Rel(service, measures, "Computes the measures each response carries")
    Rel(service, store, "Reads and writes stored sprints and events")
    Rel(service, contract, "Stamps api_version into every response")
    Rel(store, pg, "sprint_metrics schema, own user", "SQL")
    Rel(service, otel, "Logs and traces over OTLP", "OTLP")
UpdateElementStyle(entry, $borderColor="green")
```

## Where the build differs from the target

- **The response `api_version` is "4", not "3".** The target expected one
  bump per remaining epic: "2 after #752, 3 after #753". In the build each
  endpoint retirement bumped the version in its own release: GET /sprint
  retired with release 2.0.0 (`api_version` "2"), the custom Prometheus GET
  /metrics and the single-sprint response contract retired with release
  3.0.0 (`api_version` "3"), and #753's escalation removal shipped in release
  4.0.0, where `sprint_metrics.report.API_VERSION` is "4". Event intake keeps
  `api_version` "1" throughout, as the target has it.
- **The observability backend scrapes no OTEL metrics.** The target describes
  it as also scraping the service's OTEL metrics. The build emits none:
  `telemetry.py` configures only an OTLP span exporter and an OTLP log
  exporter, and the service's custom Prometheus GET /metrics endpoint — the
  only scrapeable metrics surface — was retired in 3.0.0. The diagram above
  drops the scrape from the backend's description and from the OTLP relation.
- **The two endpoint retirements are attributed to different epics.** The
  target credits both GET /sprint and GET /metrics to #752. In the build,
  GET /sprint answered 410 from story #768, which shipped in release 2.0.0
  alongside epic #751's CLI retirement, and GET /metrics was retired in epic
  #752 with release 3.0.0. The service's shape is as the target draws it;
  the diagram's labels are corrected to the releases the code shows.

Everything else in the target matches the build: the entry point runs the
service with no arguments and the CLI report tool is gone (#751); the
escalation measures are removed while the `escalated` event stays accepted
and stored (#753); all SQL lives in `store.py`; the JSON schemas are pinned
in `schemas/` at each release tag.
