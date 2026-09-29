# Default thresholds

The tool ships with built-in thresholds that determine when a metric is flagged
as breached in the JSON `flags` object and when a warning marker appears in table
and markdown output. You can override any threshold with the `--thresholds`
flag.

BEGIN:thresholds
| Metric | Default threshold | Breach direction |
|---|---|---|
| `cycle_time_days` | 5 | exceeds |
| `lead_time_days` | 7 | exceeds |
| `throughput` | 1 | falls below |
| `wip_violations` | 0 | exceeds |
| `blocked_aging_days` | 5 | exceeds |
| `escalation_rate_percent` | 10 | exceeds |
| `first_attempt_rate_percent` | 80 | falls below |
END:thresholds

## --thresholds (custom thresholds)

Override any of the default thresholds by providing a JSON file that maps
metric names to numeric threshold values. Only the metrics you specify are
overridden; all others keep their built-in defaults.

Example thresholds file (`thresholds.json`):

```json
{"cycle_time_days": 5}
```

Given a card with `created` and `started` both on `2024-01-01` and `completed`
on `2024-01-08` (cycle time 7 days, lead time 7 days):

```
sprint-metrics cards.json --thresholds thresholds.json
```

The table output flags only the breached metric with a ⚠️ marker:

```
| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate | First attempt | Top causes |
|--------|------------|-----------|------------|----------------|---------------|-----------------|---------------|------------|
| Current | 7 days ⚠️ | 7 days | 1 | 0 | 0 days | 0% | 100% | — |
```

The cycle time (7 days) exceeds the custom threshold of 5, so it is flagged.
The lead time (7 days) meets its default threshold of 7 exactly and is not
flagged (a breach requires strict greater-than).

In JSON output the `flags` object reports which metrics are breached:

```
sprint-metrics cards.json --thresholds thresholds.json --json
```

```json
{"api_version": "1", "cycle_time_days": 7, "lead_time_days": 7, "throughput": 1, "wip_violations": 0, "blocked_aging_days": 0, "escalation_rate_percent": 0, "first_attempt_rate_percent": 100, "failure_breakdown": [], "top_failure_causes": {}, "flags": {"cycle_time_days": true, "lead_time_days": false, "throughput": false, "wip_violations": false, "blocked_aging_days": false, "escalation_rate_percent": false, "first_attempt_rate_percent": false}}
```

If the thresholds file is not valid JSON, the command exits with code 2 and
prints an error to stderr:

```
sprint-metrics cards.json --thresholds bad-thresholds.json --json
# exit code: 2
# stderr: sprint-metrics: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```
