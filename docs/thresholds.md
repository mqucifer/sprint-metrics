# Default thresholds

The service's JSON responses carry a `flags` object that reports which built-in default thresholds were breached.

BEGIN:thresholds
| Metric | Default threshold | Breach direction |
|---|---|---|
| `cycle_time_days` | 5 | exceeds |
| `lead_time_days` | 7 | exceeds |
| `cycle_time_minutes` | 7200 | exceeds |
| `lead_time_minutes` | 10080 | exceeds |
| `throughput` | 1 | falls below |
| `wip_violations` | 0 | exceeds |
| `blocked_aging_days` | 5 | exceeds |
| `first_attempt_rate_percent` | 80 | falls below |
END:thresholds
