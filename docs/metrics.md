# Metrics

The table below lists the metrics the service's responses carry, their display
names, and a description of what each measures.

BEGIN:metrics
| Display name | Metric key | Description |
|---|---|---|
| Blocked aging | `blocked_aging_days` | Return the maximum number of days any card has been blocked in the sprint. |
| Cached input percent | `cached_input_percent` | Return the sprint's cached-input share of input tokens as a whole percent, or None when no story carries cost. |
| Cycle time | `cycle_time_days` | Return the sprint's average cycle time and lead time, in whole days. |
| Cycle time (min) | `cycle_time_minutes` | Return the mean cycle time in whole minutes over completed cards carrying sub-day timestamps. |
| Top causes | `failure_breakdown` | Return the returns from review or QA, grouped by (failure class, returning role), sorted by count descending. |
| First-attempt denominator | `first_attempt_denominator` | Return the total count of completed cards. |
| First-attempt numerator | `first_attempt_numerator` | Return the count of completed cards whose attempts equals 1. |
| First attempt | `first_attempt_rate_percent` | Return the percentage of completed cards that succeeded on the first attempt. |
| Input tokens (middle) | `input_tokens_middle` | Return the median input tokens across costed stories, or None when no story carries cost. |
| Input tokens (total) | `input_tokens_total` | Return the total input tokens across costed stories, or None when no story carries cost. |
| Lead time | `lead_time_days` | Return the sprint's average cycle time and lead time, in whole days. |
| Lead time (min) | `lead_time_minutes` | Return the mean lead time in whole minutes over completed cards carrying sub-day timestamps. |
| Model minutes (middle) | `model_minutes_middle` | Return the median whole model minutes across costed stories, or None when no story carries cost. |
| Model minutes (total) | `model_minutes_total` | Return the total whole model minutes across costed stories, or None when no story carries cost. |
| Output tokens (middle) | `output_tokens_middle` | Return the median output tokens across costed stories, or None when no story carries cost. |
| Output tokens (total) | `output_tokens_total` | Return the total output tokens across costed stories, or None when no story carries cost. |
| Points delivered | `points_delivered` | Return the sum of points values on completed cards. |
| Reasoning output percent | `reasoning_output_percent` | Return the sprint's reasoning share of output tokens as a whole percent, or None when no story carries cost. |
| Sent backs count | `sent_backs_count` | Return the count of distinct stories sent back to the Business Analyst in the sprint, or None when no returned events are stored. |
| Superseded breakdown | `superseded_breakdown` | Return the per-reason breakdown of superseded cards, keyed by 'sponsor' and 'story_problem' with their counts. Excluded from throughput and in-flight calculations. |
| Superseded count | `superseded_count` | Return the number of cards marked superseded in the sprint. Excluded from throughput and in-flight calculations. |
| Superseded points | `superseded_points` | Return the sum of the points value on superseded cards (0 when a superseded card carries no points value). Excluded from throughput and in-flight calculations. |
| Throughput | `throughput` | Return the number of completed cards in the sprint. |
| WIP violations | `wip_violations` | Return the number of states whose WIP limit was breached this sprint. |
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

The cost payload may also carry an optional `model_time_split` sub-object
that splits the story's model time between refinement and delivery. Its two
fields are each a non-negative integer (model seconds):

- `refinement` — model seconds spent in refinement
- `delivery` — model seconds spent in delivery

The two fields are sent together or not at all; a partial sub-object is
rejected at intake. The sub-object is independent of the five cost fields:
a finished event may carry the split without the five fields, or the five
fields without the split.

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

### Rework (send-backs to refinement and review/QA returns)

The `rework` answer on each sprint's `/range` entry covers the whole
pipeline: the send-backs to refinement and the review/QA returns, each
labeled and separated, so the reader cannot conflate the two kinds of
rework. `rework.started` is the count of distinct stories with a
`started` event in the sprint.

`rework.sent_backs` names the stories the crew handed back to the
Business Analyst — its `returned` events — out of the stories started
that sprint. Each sent-back story is named once, by its identifier, and
each send-back carries the step it was sent back from (the role that
sent it back, as sent on the event) and the reason, in words a public
visitor can read. A send-back counts in the sprint of the `returned`
event, not the sprint the story started in, and a story sent back more
than once in a sprint is named once with each send-back.

`rework.qa_returns` names the stories bounced at review or QA — its
`attempt_failed` events (or, in the legacy case, a finished card with
attempts greater than 1). Each returned story is named once, by its
identifier, and each return carries the step it was returned from (the
returning role) and the cause, using the same (failure class, returning
role) values as `failure_breakdown`. A story that both went back to the
Business Analyst and bounced at review or QA appears in both parts,
separately.

`rework.by_step` groups each part's returns by step (the count of
rework per step), so the reader sees which step the sprint's rework
concentrates in, and comparing sprints across a `/range` window shows
where work leaks across sprints, not just a per-sprint snapshot.

A `returned` event completes no story: it changes none of the other
metrics (throughput, cycle time, lead time, failure breakdown, and the
like keep their values and shape). Pre-rollout history reads as no
data, not zero: a sprint with no events carries `rework` null, a sprint
with events but no stored `returned` events carries its started count
with `sent_backs` null, and a sprint with no review/QA returns carries
`qa_returns` null — each part names no story and does not assert a zero
count, and the two parts do not borrow each other's data.

## Boundary conditions

### Zero values for an empty sprint

A sprint with no completed cards reports 0 for cycle time, lead time,
throughput, points delivered, first-attempt numerator, first-attempt
denominator, and first-attempt rate. WIP violations is 0
when no WIP limits are configured.

### Points delivered for a card without a points value

A completed card with no `points` value contributes 0 to the points
delivered total.

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
