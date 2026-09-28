# Command-line usage

The `sprint-metrics` command reads a JSON file of sprint cards (or stdin) and
reports delivery metrics. The most common invocation is:

```
sprint-metrics cards.json
```

Omit the file argument to read from standard input. Use `--help` for a full
list of options.

BEGIN:cli-args
- `cards`: JSON file of sprint cards; reads stdin when omitted. (default: <_io.TextIOWrapper name='<stdin>' mode='r' encoding='utf-8'>)
- `--wip-limits`: JSON file of WIP limits keyed by state, e.g. {"In Progress": 3}; without it no limits apply.
- `--escalations`: Number of escalations to apply to each sprint in the range. (default: 0)
- `--sprint-date`: ISO-8601 date to measure blocked aging against (default: today).
- `--sprint-range`: Inclusive range of YYYY-MM sprint labels, e.g. 2024-01..2024-03. The cards file must be a JSON object keyed by sprint label.
- `--prior-sprint`: A prior sprint label (YYYY-MM) to compare against in the markdown report. The cards file must be a JSON object keyed by sprint label.
- `--prior`: JSON file of prior-period cards, shown as a second row in the default table.
- `--markdown`: Output the report as markdown instead of the default table format. (default: False)
- `--prometheus`: Output the report in Prometheus text exposition format. (default: False)
- `--json`: Output the report as a JSON object. (default: False)
- `--schema`: Output the JSON Schema for the API response (requires --json). (default: False)
- `--scrape`: Start an HTTP server that serves the metrics at /metrics for scraping. (default: False)
- `--port`: Port for the scrape server (default: 9100). Use 0 for an ephemeral port. (default: 9100)
- `--thresholds`: JSON file of metric thresholds keyed by metric name, e.g. {"cycle_time_days": 3}; overrides the built-in defaults for the metrics it specifies.
- `--metrics`: Comma-separated list of metric names to include in the output.
END:cli-args
