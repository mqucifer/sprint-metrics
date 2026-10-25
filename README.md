# sprint-metrics

Reports how the crew is performing: cycle time, lead time, throughput per sprint, WIP-limit violations, blocked-card aging, escalation rate, first-attempt rate, and failure breakdown. The service accepts board events over HTTP and answers sprint, range, and trend queries from that history.

## Installation

### Git dependency

Requires Python 3.12. The tool requires the following third-party runtime packages: psycopg, opentelemetry-sdk, and opentelemetry-exporter-otlp.

### From git

```
uv pip install git+https://github.com/mqucifer/sprint-metrics.git@v0.1.0
```

### From a container image

```
docker pull ghcr.io/mqucifer/sprint-metrics:1.0.0
```

Image tags follow the pattern `X.Y.Z`, `X.Y`, and `latest`.

### Container image

No Python interpreter or third-party packages are required on the host — the image is self-contained. The released image is the way to run the service.

```
docker run -d -p 8080:8080 \
  -e SPRINT_METRICS_DB=postgresql://sprint:secret@db.internal:5432/sprint_metrics \
  ghcr.io/mqucifer/sprint-metrics:1.0.0
```

The image is available under a version tag matching each release (e.g. `1.0.0`) and under the tag `latest` for the newest version.

## Basic usage

```
docker run -d -p 8080:8080 \
  -e SPRINT_METRICS_DB=postgresql://sprint:secret@db.internal:5432/sprint_metrics \
  ghcr.io/mqucifer/sprint-metrics:1.0.0
```

The service listens on port 8080 and accepts board events over HTTP. See [docs/service.md](docs/service.md) for the full endpoint reference.

Full documentation lives in [docs/](docs/): metric definitions, thresholds, and the service endpoints.

## JSON Schemas

Every API endpoint has a JSON Schema that defines its response (or request) shape. The schemas live in `schemas/` at the repository root. Each is pinned to the release tag you run.

| File | Direction | Endpoint |
|---|---|---|
| `schemas/event-intake.json` | sent — the request body the service validates | POST /events |
| `schemas/sprint-range.json` | received — the response you validate | GET /range |
| `schemas/trend.json` | received — the response you validate | GET /trend |

**Direction.** "Sent" means the schema describes the input the service validates before accepting an event. "Received" means the schema describes the output the service returns. Validate your POST /events body against the sent schema; validate the service's response against the received schema for the endpoint you called.

**Fetch a schema at a tag.** Replace `v1.3.3` with the version tag you run:

```
curl https://raw.githubusercontent.com/mqucifer/sprint-metrics/v1.3.3/schemas/sprint-range.json
```

If you already have a clone:

```
git show v1.3.3:schemas/sprint-range.json
```

**You do not keep a copy.** Point your validation library at the schema URL for the tag you run, or pin the tag in a CI check. The schema at the tag is the contract; a local copy goes stale.

## Versioning

Versions follow SemVer:

- **MAJOR** — removing a published API version
- **MINOR** — adding a feature or a new API version
- **PATCH** — fixes and documentation changes

Release notes are published as GitHub Releases on the [sprint-metrics repository](https://github.com/mqucifer/sprint-metrics/releases). The [CHANGELOG.md](CHANGELOG.md) file in the repository tracks changes between versions.

CI checks `CHANGELOG.md` for four invariants on every pull request:

1. The version in `pyproject.toml` equals the newest released section's version in `CHANGELOG.md`.
2. Released sections run newest first by version, and no released section's date is later than the date of the section above it or later than the day the check runs.
3. `## [Unreleased]` is the first section, with the subheadings Added, Changed, Fixed, and Removed in that order.
4. Every released section's heading is dated `YYYY-MM-DD`.

A section's content — the entries under its subheadings — is not checked by tests; entries are checked by review, not by CI.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the version-to-version change history.

## Documentation maintenance

User-visible changes update `docs/` and `CHANGELOG.md` in the same pull request.
