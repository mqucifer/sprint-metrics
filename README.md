# sprint-metrics

Reports how the crew is performing: cycle time, lead time, throughput per sprint, WIP-limit violations, blocked-card aging, escalation rate, first-attempt rate, and failure breakdown — as a table, as JSON, as markdown, and as Prometheus metrics for scrape mode.

## Installation

Requires Python 3.12. No third-party runtime packages are needed — the tool uses only the standard library.

```
uv pip install git+https://github.com/mqucifer/sprint-metrics.git@v0.1.0
```

After installation the `sprint-metrics` command is available on the PATH.

## Basic usage

```
sprint-metrics cards.json
```

`cards.json` is a JSON file of sprint cards. When no file argument is given, the tool reads the JSON from standard input and prints the default table.

Full documentation lives in [docs/](docs/): card input format, metric definitions, output formats, thresholds, and scrape mode.
