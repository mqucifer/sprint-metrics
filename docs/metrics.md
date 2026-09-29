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

## Computation details

### First attempt rate

The first attempt rate is the percentage of completed cards whose `attempts`
field equals 1, rounded to the nearest whole number. A sprint with no
completed cards reports 0.

### Failure breakdown

The failure breakdown includes only completed cards with `attempts` greater
than 1. Cards are grouped by their failure class and failure role, and the
groups are sorted by count descending. The result is an empty list when no
completed card has attempts greater than 1.

### Top failure causes

Top failure causes is the top 3 failure classes by count, with ties broken
alphabetically. The result is an empty object when no completed card has a
non-null failure class.
