# 7. Logs and traces as OpenTelemetry over OTLP

- **Date:** 2026-10-01
- **Status:** Accepted

## Context

The service fits into how its users already watch their systems.

## Decision

The service emits its logs and traces as OpenTelemetry over OTLP, with no custom collector in between. Its metrics can be scraped.

## Consequences

The OpenTelemetry SDK and the OTLP exporter are runtime dependencies. Where they send to is a setting.

## Source

The service Goal and its decision D9 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)); mqucifer/crew#283 ([issue](https://github.com/mqucifer/crew/issues/283)).
