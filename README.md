# sprint-metrics

Reports how the crew is performing: cycle time, lead time, throughput per sprint, WIP-limit violations, blocked-card aging, escalation rate, first-attempt rate, and failure breakdown — as a table, as JSON, as markdown, and as Prometheus metrics for scrape mode.

## Installation

### Git dependency

Requires Python 3.12. No third-party runtime packages are needed — the tool uses only the standard library.

### From git

```
uv pip install git+https://github.com/mqucifer/sprint-metrics.git@v0.1.0
```

### From a container image

```
docker pull ghcr.io/mqucifer/sprint-metrics:1.0.0
```

Image tags follow the pattern `X.Y.Z`, `X.Y`, and `latest`.

After installation the `sprint-metrics` command is available on the PATH.

### Container image

No Python interpreter or third-party packages are required on the host — the image is self-contained.

```
docker run --rm -v /path/to/cards.json:/input/cards.json ghcr.io/mqucifer/sprint-metrics:1.0.0 /input/cards.json
```

The cards file is mounted into the container at `/input/cards.json`, and the command produces a table report on stdout.

The image is available under a version tag matching each release (e.g. `1.0.0`) and under the tag `latest` for the newest version.

## Basic usage

```
sprint-metrics cards.json
```

`cards.json` is a JSON file of sprint cards. When no file argument is given, the tool reads the JSON from standard input and prints the default table.

Full documentation lives in [docs/](docs/): card input format, metric definitions, output formats, thresholds, and scrape mode.

## Versioning

Versions follow SemVer:

- **MAJOR** — removing a published API version
- **MINOR** — adding a feature or a new API version
- **PATCH** — fixes and documentation changes

Release notes are published as GitHub Releases on the [sprint-metrics repository](https://github.com/mqucifer/sprint-metrics/releases). The [CHANGELOG.md](CHANGELOG.md) file in the repository tracks changes between versions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the version-to-version change history.

## Documentation maintenance

User-visible changes update `docs/` and `CHANGELOG.md` in the same pull request.
