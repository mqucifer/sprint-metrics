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

## --schema

The `--schema` flag outputs the JSON Schema for the API response to stdout.
It requires `--json`; without it the command exits with an error (exit code 2).
No cards file is needed.

```
sprint-metrics --schema --json
```

The output is a single-line JSON object (the JSON Schema, draft 2020-12):

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "required": ["api_version", "cycle_time_days", "lead_time_days", "throughput", "wip_violations", "blocked_aging_days", "escalation_rate_percent", "first_attempt_rate_percent", "failure_breakdown", "top_failure_causes", "flags"], "properties": {"api_version": {"type": "string"}, "cycle_time_days": {"type": "integer"}, "lead_time_days": {"type": "integer"}, "throughput": {"type": "integer"}, "wip_violations": {"type": "integer"}, "blocked_aging_days": {"type": "integer"}, "escalation_rate_percent": {"type": "integer"}, "first_attempt_rate_percent": {"type": "integer"}, "failure_breakdown": {"type": "array", "items": {"type": "object", "properties": {"class": {"type": "string"}, "role": {"type": "string"}, "count": {"type": "integer"}}, "required": ["class", "role", "count"]}}, "top_failure_causes": {"type": "object"}, "flags": {"type": "object"}, "sprint_date": {"type": "string"}, "prior": {"type": "object", "properties": {"cycle_time_days": {"type": "integer"}, "lead_time_days": {"type": "integer"}, "throughput": {"type": "integer"}, "wip_violations": {"type": "integer"}, "blocked_aging_days": {"type": "integer"}, "escalation_rate_percent": {"type": "integer"}, "first_attempt_rate_percent": {"type": "integer"}, "top_failure_causes": {"type": "object"}}}, "delta": {"type": "object", "properties": {"cycle_time_days": {"type": "integer"}, "lead_time_days": {"type": "integer"}, "throughput": {"type": "integer"}, "wip_violations": {"type": "integer"}, "blocked_aging_days": {"type": "integer"}, "escalation_rate_percent": {"type": "integer"}, "first_attempt_rate_percent": {"type": "integer"}}}}}
```

Omitting `--json` produces an error:

```
$ sprint-metrics --schema
sprint-metrics: --schema is only valid with --json
```

Exit code: 2.

## --sprint-range

The `--sprint-range` flag reports on multiple sprints at once. The cards file must be a JSON object keyed by `YYYY-MM` sprint label, each value a list of cards. The range is inclusive: `START..END` produces one table row for every label from START to END.

```json
{
  "2024-01": [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}],
  "2024-02": [{"created": "2024-02-01", "started": "2024-02-03", "completed": "2024-02-07"}]
}
```

```
sprint-metrics sprints.json --sprint-range 2024-01..2024-02
```

```
| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate | First-attempt | Top failure causes |
|--------|------------|-----------|------------|----------------|---------------|-----------------|-------------|------------------|
| 2024-01 | 4 days | 6 days | 1 | 0 | 0 days | 0% | 100% | — |
| 2024-02 | 4 days | 6 days | 1 | 0 | 0 days | 0% | 100% | — |
```

If the range includes a sprint label not present in the file, the command exits with code 2 and names the missing label on stderr:

```
$ sprint-metrics sprints.json --sprint-range 2024-01..2024-02
sprint-metrics: no data for sprint 2024-02
```

## --prior-sprint

The `--prior-sprint` flag compares the most recent sprint against a prior one in a markdown report. The cards file must be a JSON object keyed by `YYYY-MM` sprint label (not a plain array), and the prior label must not be the most recent sprint.

```json
{
  "2024-01": [{"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-08"}],
  "2024-02": [{"created": "2024-02-01", "started": "2024-02-03", "completed": "2024-02-07"}]
}
```

```
sprint-metrics sprints.json --prior-sprint 2024-01 --markdown
```

The markdown output includes a `## Prior Sprint` section with the prior sprint's metrics and a `## Current Sprint` section where each metric line shows the prior value and the signed change:

```
# Crew Performance Report

Report date: 2024-02-10

## Prior Sprint 2024-01

- **Cycle time**: 6 days
- **Lead time**: 7 days
- **Throughput**: 1 cards
- **WIP violations**: 0
- **Blocked aging**: 0 days
- **Escalation rate**: 0%
- **First-attempt rate**: 100%

## Current Sprint

- **Cycle time**: 4 days (was 6 days, -2)
- **Lead time**: 6 days (was 7 days, -1)
- **Throughput**: 1 (was 1, 0)
- **WIP violations**: 0 (was 0, 0)
- **Blocked aging**: 0 days (was 0 days, 0)
- **Escalation rate**: 0% (was 0%, 0)
- **First-attempt rate**: 100% (was 100%, 0)

## Crew Performance Summary

- **Completed**: 1
- **In progress**: 0
- **Blocked**: 0
```

The report date reflects the day the example was captured. The `--prior-sprint` flag works with `--markdown` and `--json`; without `--markdown`, the default table output ignores the prior sprint.

If the prior label is the most recent sprint, the command exits with code 2:

```
$ sprint-metrics sprints.json --prior-sprint 2024-02 --markdown
sprint-metrics: prior sprint '2024-02' cannot be the most recent sprint
```

Exit code: 2.
## --prior

The `--prior` flag compares the current period against a prior one by supplying two separate JSON files of cards. The current cards file is the primary argument; the prior cards file is passed with `--prior`. The default table shows three rows: `Current`, `Prior`, and `Delta`, where the Delta row shows the signed difference (Current minus Prior) for each numeric metric.

Current cards file (`current.json`):

```json
[{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
```

Prior cards file (`prior.json`):

```json
[{"created": "2023-12-01", "started": "2023-12-03", "completed": "2023-12-09"}]
```

```
sprint-metrics current.json --prior prior.json
```

```
| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate | First-attempt | Top failure causes |
|--------|------------|-----------|------------|----------------|---------------|-----------------|-------------|------------------|
| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% | 100% | — |
| Prior | 6 days | 8 days | 1 | 0 | 0 days | 0% | 100% | — |
| Delta | -2 days | -2 days | 0 | 0 | 0 days | 0% | 0% | — |
```

If the prior file contains invalid JSON, the command exits with code 2 and reports the error on stderr:

```
$ sprint-metrics current.json --prior prior.json
sprint-metrics: Expecting value: line 1 column 1 (char 0)
```

Exit code: 2.
