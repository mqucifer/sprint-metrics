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
