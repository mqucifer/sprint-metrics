# Metrics

The table below lists every metric the tool computes, its display name, a
description of what it measures, and the Prometheus metric name used in
scrape mode.

BEGIN:metrics
| Display name | Metric key | Description | Prometheus name |
|---|---|---|---|
| Blocked aging | `blocked_aging_days` | Return the maximum number of days any card has been blocked in the sprint. | `sprint_blocked_aging_days` |
| Cycle time | `cycle_time_days` | Return the sprint's average cycle time and lead time, in whole days. | `sprint_cycle_time_days` |
| Escalation rate | `escalation_rate_percent` | Return the escalation rate as a percentage (0-100). | `sprint_escalation_rate_percent` |
| Top causes | `failure_breakdown` | Return the failure causes grouped by (class, role), sorted by count descending. | `sprint_failure_count` |
| First attempt | `first_attempt_rate_percent` | Return the percentage of completed cards that succeeded on the first attempt. | `sprint_first_attempt_rate_percent` |
| Lead time | `lead_time_days` | Return the sprint's average cycle time and lead time, in whole days. | `sprint_lead_time_days` |
| Throughput | `throughput` | Return the number of completed cards in the sprint. | `sprint_throughput` |
| WIP violations | `wip_violations` | Return the number of states whose WIP limit was breached this sprint. | `sprint_wip_violations` |
END:metrics
