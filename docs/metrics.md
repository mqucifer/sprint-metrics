# Metrics

The table below lists every metric the tool computes, its display name, a
description of what it measures, and the Prometheus metric name used in
scrape mode.

BEGIN:metrics
| Display name | Metric key | Description | Prometheus name |
|---|---|---|---|
| Blocked aging | `blocked_aging_days` | Return the maximum number of days any card has been blocked in the sprint. | `sprint_blocked_aging_days` |
| Cached input percent | `cached_input_percent` | Return the sprint's cached-input share of input tokens as a whole percent, or None when no story carries cost. | `sprint_cached_input_percent` |
| Cycle time | `cycle_time_days` | Return the sprint's average cycle time and lead time, in whole days. | `sprint_cycle_time_days` |
| Cycle time (min) | `cycle_time_minutes` | Return the mean cycle time in whole minutes over completed cards carrying sub-day timestamps. | `sprint_cycle_time_minutes` |
| Escalation count | `escalation_count` | Return the number of escalated events in the sprint. | `sprint_escalation_count` |
| Escalation rate | `escalation_rate_percent` | Return the escalation rate as a whole-number percentage of escalations over completed cards; 0 when no cards are completed. | `sprint_escalation_rate_percent` |
| Top causes | `failure_breakdown` | Return the returns from review or QA, grouped by (failure class, returning role), sorted by count descending. | `sprint_failure_count` |
| First-attempt denominator | `first_attempt_denominator` | Return the total count of completed cards. | `sprint_first_attempt_denominator` |
| First-attempt numerator | `first_attempt_numerator` | Return the count of completed cards whose attempts equals 1. | `sprint_first_attempt_numerator` |
| First attempt | `first_attempt_rate_percent` | Return the percentage of completed cards that succeeded on the first attempt. | `sprint_first_attempt_rate_percent` |
| Input tokens (middle) | `input_tokens_middle` | Return the median input tokens across costed stories, or None when no story carries cost. | `sprint_input_tokens_middle` |
| Input tokens (total) | `input_tokens_total` | Return the total input tokens across costed stories, or None when no story carries cost. | `sprint_input_tokens_total` |
| Lead time | `lead_time_days` | Return the sprint's average cycle time and lead time, in whole days. | `sprint_lead_time_days` |
| Lead time (min) | `lead_time_minutes` | Return the mean lead time in whole minutes over completed cards carrying sub-day timestamps. | `sprint_lead_time_minutes` |
| Model minutes (middle) | `model_minutes_middle` | Return the median whole model minutes across costed stories, or None when no story carries cost. | `sprint_model_minutes_middle` |
| Model minutes (total) | `model_minutes_total` | Return the total whole model minutes across costed stories, or None when no story carries cost. | `sprint_model_minutes_total` |
| Output tokens (middle) | `output_tokens_middle` | Return the median output tokens across costed stories, or None when no story carries cost. | `sprint_output_tokens_middle` |
| Output tokens (total) | `output_tokens_total` | Return the total output tokens across costed stories, or None when no story carries cost. | `sprint_output_tokens_total` |
| Points delivered | `points_delivered` | Return the sum of points values on completed cards. | `sprint_points_delivered` |
| Reasoning output percent | `reasoning_output_percent` | Return the sprint's reasoning share of output tokens as a whole percent, or None when no story carries cost. | `sprint_reasoning_output_percent` |
| Superseded breakdown | `superseded_breakdown` | Return the per-reason breakdown of superseded cards, keyed by 'sponsor' and 'story_problem' with their counts. Excluded from throughput and in-flight calculations. | `sprint_metrics_superseded_by_reason` |
| Superseded count | `superseded_count` | Return the number of cards marked superseded in the sprint. Excluded from throughput and in-flight calculations. | `sprint_metrics_superseded_stories` |
| Superseded points | `superseded_points` | Return the sum of the points value on superseded cards (0 when a superseded card carries no points value). Excluded from throughput and in-flight calculations. | `sprint_metrics_superseded_points` |
| Throughput | `throughput` | Return the number of completed cards in the sprint. | `sprint_throughput` |
| WIP violations | `wip_violations` | Return the number of states whose WIP limit was breached this sprint. | `sprint_wip_violations` |
END:metrics

## Computation details

### First attempt rate

The first attempt rate is the percentage of completed stories accepted by
review and QA on the first hand to them, rounded to the nearest whole number.
An attempt is a hand of the story to review or QA; the crew's own checks
before review do not count as attempts. A sprint with no completed stories
reports 0.

### Failure breakdown

The failure breakdown counts returns, not failed stories: one entry per
return by review or QA, grouped by (failure class, returning role), sorted
by count descending. The result is an empty list when no completed story has
a return.

### Top failure causes

Top failure causes is the top 3 returns keyed by (failure class, returning
role), count descending, ties broken alphabetically. The result is an empty
list when no return was recorded.

### Superseded metrics

`superseded_count` is the number of cards in the sprint that carry a
superseded event. A superseded story is neither delivered — it is excluded
from throughput, cycle time, and lead time — nor in-flight — it is excluded
from WIP occupancy and blocked aging. It is a distinct state from both.

`superseded_points` is the sum of the `points` value on the cards that were
superseded in the sprint. It is 0 when no superseded card carries a points
value.

`superseded_breakdown` is an object with two keys, `"sponsor"` and
`"story_problem"`, giving the count of superseded stories for each reason.
Both keys are always present, even when one of the reasons has no superseded
stories.

### Cycle time and lead time (minutes)

`cycle_time_minutes` is the mean of (completed_at − started_at) over all
completed cards that carry both a `started_at` and a `completed_at`
timestamp, expressed in whole minutes and rounded to the nearest integer.

`lead_time_minutes` is the mean of (completed_at − created_at) over all
completed cards that carry both a `created_at` and a `completed_at`
timestamp, expressed in whole minutes and rounded to the nearest integer.

### Model cost

The crew's event-sending automation attaches a cost payload to each
`finished` event it sends. The payload carries five fields, each a
non-negative integer:

- `model_seconds` — total model time across every role's calls for this story
- `input_tokens` — total input tokens consumed
- `cached_input_tokens` — input tokens served from cache
- `output_tokens` — total output tokens produced
- `reasoning_output_tokens` — output tokens spent on reasoning

All five fields are sent together or not at all; a partial payload is
rejected at intake.

The report's display unit for model cost is whole minutes. The crew sends
model seconds on the event; the report shows `round(model_seconds / 60)`
as `model_minutes`.

A story's cost is the summed total across every role's model calls for that
story. The sprint's cost summary reports two aggregates per measure
(`model_minutes`, `input_tokens`, `output_tokens`):

- **middle** — the median of the per-story values across all costed stories
- **total** — the sum across the costed stories

The two percents, `cached_input_percent` and `reasoning_output_percent`,
are computed from the sprint's combined token totals, not per story:
`cached_input_percent` is the sprint's cached-input share of all input
tokens, and `reasoning_output_percent` is the sprint's reasoning share of
all output tokens. Both percents are identical on every story in the
`story_costs` list.

## Boundary conditions

### Zero values for an empty sprint

A sprint with no completed cards reports 0 for cycle time, lead time,
throughput, points delivered, first-attempt numerator, first-attempt
denominator, escalation rate, and first-attempt rate. WIP violations is 0
when no WIP limits are configured.

### Points delivered for a card without a points value

A completed card with no `points` value contributes 0 to the points
delivered total.

### Escalation count

The escalation count is the number of escalated events in the sprint. It is
the numerator behind the escalation-rate percentage, whose denominator is
throughput. It reflects only the escalations parameter (CLI) or event count
(service) regardless of whether any card is completed. It is 0 when no
escalations are recorded.

### Cycle time for a card without a started date

A card completed without a `started` date contributes 0 days to the
cycle-time average.

### Blocked aging reference date

For a card that was blocked and later completed, blocked aging is measured
from `blocked_since` to the completion date. For a card still blocked,
blocked aging is measured from `blocked_since` to the reference date, which
defaults to today.

### WIP violations

WIP violations counts the number of states whose peak simultaneous
occupancy exceeded the configured limit. A state with no configured limit
cannot be in violation.

### Escalation rate with no completed cards

Escalation rate is 0 when no cards are completed, regardless of the
escalation count.

### Superseded

A sprint with no superseded events reports 0 for `superseded_count`, 0 for
`superseded_points`, and `{'sponsor': 0, 'story_problem': 0}` for
`superseded_breakdown`. A superseded story is excluded from both throughput
and in-flight calculations; it does not contribute to any in-flight or
delivered metric.

### Minute-level metrics null behavior

`cycle_time_minutes` is null (not 0) when no completed card carries both a
`started_at` and a `completed_at` timestamp. `lead_time_minutes` is null when
no completed card carries both a `created_at` and a `completed_at` timestamp.
Cards that provide only the date-only fields (`started`, `completed`,
`created`) do not contribute to the minute-level metrics.
