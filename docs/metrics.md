# Metrics

The table below lists the metrics the service's responses carry, their display
names, and a description of what each measures.

BEGIN:metrics
| Display name | Metric key | Description |
|---|---|---|
| Addition working time | `addition_working_time_minutes` | Return the sprint's working time for stories whose kind is 'addition', in whole minutes. None when no stored story row in the sprint carries a kind. |
| Blocked aging | `blocked_aging_days` | Return the maximum number of whole days any card has been blocked in the sprint, in whole days. |
| Cached input percent | `cached_input_percent` | Return the sprint's cached-input share of input tokens as a whole percent, or None when no story carries cost. |
| DORA change failure count | `change_failure_count` | Return the count of the sprint's releases that came back with rework (a 'returned' event on a story of the epic after the release moment), as a whole count, shown alongside its rate. None when no epic link is derivable. |
| DORA change failure rate | `change_failure_rate_percent` | Return the share of the sprint's releases that came back with rework, as a whole percent (the change-failure rate), shown alongside its count. None when no epic link is derivable. |
| Change working time | `change_working_time_minutes` | Return the sprint's working time for stories whose kind is 'change', in whole minutes. None when no stored story row in the sprint carries a kind. |
| Cycle time | `cycle_time_days` | Return the sprint's average cycle time and lead time, in whole days. |
| Cycle time (min) | `cycle_time_minutes` | Return the mean cycle time in whole minutes over completed cards carrying sub-day timestamps. |
| DORA lead time for changes | `dora_lead_time_days` | Return the mean, in whole days from story creation to the epic's release moment, over each released story. None when no epic link is derivable. |
| Top causes | `failure_breakdown` | Return the returns from review or QA, grouped by (failure class, returning role), sorted by count descending. |
| First-attempt denominator | `first_attempt_denominator` | Return the total count of completed cards, as a whole count. |
| First-attempt numerator | `first_attempt_numerator` | Return the count of completed cards whose attempts equals 1, as a whole count. |
| First attempt | `first_attempt_rate_percent` | Return the percentage of completed cards that succeeded on the first attempt, as a whole percent. |
| Idle time | `idle_minutes` | Return the sprint's idle time — the time that passed with no session running against the sprint's total registered duration — in whole minutes (the registered span minus the in-span session time, in the sprint's registered timezone; a session window clamped to the span, a rework session never re-sent as 'started' reads as idle). None where the sprint is not registered or no session ran inside the span. |
| Input tokens (middle) | `input_tokens_middle` | Return the median input tokens across costed stories, as a whole count, or None when no story carries cost. |
| Input tokens (total) | `input_tokens_total` | Return the total input tokens across costed stories, as a whole count, or None when no story carries cost. |
| Lead time | `lead_time_days` | Return the sprint's average cycle time and lead time, in whole days. |
| Lead time (min) | `lead_time_minutes` | Return the mean lead time in whole minutes over completed cards carrying sub-day timestamps. |
| DORA mean time to recovery | `mean_time_to_recovery_minutes` | Return the mean, in whole minutes, of the completed recovery spans (from the 'returned' event to the epic's next release moment) over the sprint's bad releases that re-released. None when no epic link is derivable, or no bad release has completed a recovery. |
| Model minutes (middle) | `model_minutes_middle` | Return the median whole model minutes across costed stories, or None when no story carries cost. |
| Model minutes (total) | `model_minutes_total` | Return the total whole model minutes across costed stories, or None when no story carries cost. |
| Model time split (delivery) | `model_time_split_delivery_minutes` | Return the sprint's model time spent in delivery, in whole minutes — each story's delivery seconds converted to whole minutes (the model_minutes display unit) and summed over the costed stories. None when no story in the sprint carries a model-time split. |
| Model time split (refinement) | `model_time_split_refinement_minutes` | Return the sprint's model time spent in refinement, in whole minutes — each story's refinement seconds converted to whole minutes (the model_minutes display unit) and summed over the costed stories. None when no story in the sprint carries a model-time split. |
| Output tokens (middle) | `output_tokens_middle` | Return the median output tokens across costed stories, as a whole count, or None when no story carries cost. |
| Output tokens (total) | `output_tokens_total` | Return the total output tokens across costed stories, as a whole count, or None when no story carries cost. |
| Points delivered | `points_delivered` | Return the sum of points values on completed cards, in whole points. |
| Reasoning output percent | `reasoning_output_percent` | Return the sprint's reasoning share of output tokens as a whole percent, or None when no story carries cost. |
| DORA release frequency | `release_frequency` | Return the count of distinct epics released in the sprint (how often epics ship), as a whole count. None when no epic link is derivable. |
| Sent backs count | `sent_backs_count` | Return the count of distinct stories sent back to the Business Analyst in the sprint, or None when no returned events are stored. |
| Superseded breakdown | `superseded_breakdown` | Return the per-reason breakdown of superseded cards, keyed by 'sponsor' and 'story_problem' with their counts. Excluded from throughput and in-flight calculations. |
| Superseded count | `superseded_count` | Return the count of cards marked superseded in the sprint, as a whole count. Excluded from throughput and in-flight calculations. |
| Superseded points | `superseded_points` | Return the sum of the points value on superseded cards, in whole points (0 when a superseded card carries no points value). Excluded from throughput and in-flight calculations. |
| Throughput | `throughput` | Return the count of completed cards in the sprint, as a whole count. |
| WIP violations | `wip_violations` | Return the count of states whose WIP limit was breached this sprint, as a whole count. |
| Working time | `working_time_minutes` | Return the sprint's working-time total, in whole minutes — the sum of the crew's session windows (from a story's started row to its returned/attempt_failed/finished row, a blocked card's blocked interval not counted), per step of the story's pipeline. None when no card carries a closed session window. |
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

### Working time per pipeline step

The `working_time` answer on each sprint's `/range` entry carries the
minutes the crew's sessions ran, per step of a story's pipeline. A session
window runs from a story's `started` row to the story's next terminal row
(`finished`, `attempt_failed`, or `returned`); the story's working time is
the sum of its windows, and the sprint's is the sum across its stories. The
step a window belongs to is the role sent on its terminal row when that row
is an `attempt_failed` or `returned` row (the row that marks the step
boundary), or, for a window closed by `finished`, the step it is reworking.
`working_time.per_step` carries one value per session window, and
`working_time.total` is their sum in whole minutes.

Working time is the minutes the crew's sessions ran, not the span from the
story's creation to its finish: it is measured session by session, so the
calendar gap between one session and the next — and any time a card sat
unworked — never counts. A rework session that the crew never re-sent as
`started` is invisible to working time and shows as idle time instead; this
is the fidelity bound, set by the granularity of the events the crew sends.
A blocked card's blocked interval is not working time: while the story is
blocked, the crew's clock does not run, so a session's minutes are its span
minus the minutes it was blocked.

A sprint whose cards carry no session timestamps (date-only fields) or whose
sessions never closed reports `working_time` null, not zero, matching the
null behaviour of the other minute-based metrics.

### Idle time against the sprint's duration

The `idle` answer on each sprint's `/range` entry carries the idle time — the
time that passed with no session running — against the sprint's total
registered duration, in whole minutes.

The total duration (`idle.sprint_duration_minutes`) is the sprint's registered
span, from the start of the registered start date to the end of the registered
end date, taken in the sprint's registered timezone: the span is the real
elapsed time in that zone, so a day the calendar does not turn twenty-four
hours (a DST transition) reads as the minutes that actually elapsed.

The idle time (`idle.idle_minutes`) is the registered span minus the in-span
session time, in whole minutes. A session window is clamped to the span — only
the part of a window inside the registered span counts as session time, so a
window that runs past the end date (or starts before the start date) counts
only its in-span part. A blocked card's blocked interval within a clamped
window is not session time, the way it is not working time.

Because a session window opens only on a `started` row, a rework session the
crew never re-sent as `started` contributes no session time and reads as idle —
the working-time fidelity bound, set by the granularity of the events the crew
sends.

A sprint with no events, or with no registered definition, reads `idle` null,
matching the null behaviour of the other minute-based metrics. Where the sprint
is registered but no session ran inside the span, `idle.sprint_duration_minutes`
carries the span and `idle.idle_minutes` is null — the whole span is not
reported as idle when no session ran. The flat `idle_minutes` name also appears
in each later sprint's `prior` and `delta`, null where a sprint has no data.

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

### Model time split (refinement against delivery)

`model_time_split_refinement_minutes` and
`model_time_split_delivery_minutes` split the sprint's model time between
refinement and delivery. The unit is whole minutes, the model_minutes
display unit: the crew sends model seconds on each story's finished event
(`model_time_split`'s `refinement` and `delivery` fields), and each story's
two values are converted to whole minutes (rounded) before the sprint's
totals sum them across the costed stories. The pair lets a reader see,
sprint by sprint, how much model time went to refinement and how much to
delivery.

A sprint whose stories carry no model-time split — the pre-Goal payloads
that carry the five-field cost but no split, or a sprint with no costed
stories at all — reports both measures as null, not zero: no data, matching
the null behaviour of the other minute-based metrics.

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

### Filed split (how much of the sprint's filed work the crew gave itself)

The `filed` answer on each sprint's `/range` entry reports how much of the
sprint's filed work the crew gave itself, beside what the Sponsor, the
operator and anyone else filed. Every value is a whole count of cards.

A card counts in the sprint it was filed in — the sprint named on its `filed`
event — not the sprint it merged in. The filed total therefore differs from
throughput by design: a card filed in one sprint and merged in another counts
in the filed answer for the sprint that filed it, not the sprint that shipped
it.

The buckets partition the sprint. The crew's own filed cards split into four
buckets — `found` (a role found a problem), `from_process` (the crew's own
test, release, review or technical debt), `split` (split from already-filed
work) and `unknown` (the crew filed it, but it can't be told what opened it)
— and the four sum to the crew-filed total: `crew_total = found +
from_process + split + unknown`. The filers partition the rest of the
sprint's filed cards: the Sponsor's (`sponsor`), the operator's (`operator`)
and everyone else's (`other`), which together with the crew equal the
sprint's total filed cards: `crew_total + sponsor + operator + other =
total_cards`.

The `unknown` bucket is counted in the crew total: those cards were filed by
the crew, they simply can't be told apart. A card the crew can't place is
reported as `unknown`, never guessed into another bucket.

`self_filed_share` carries the whole percent of the sprint's total filed
cards that the crew filed, with its numerator (`crew_total`) and denominator
(`total_cards`), so the share reads "25 of 27" without arithmetic.

No data is kept distinct from zero. A sprint with events but no stored
`filed` events reads `filed` null — no filing facts, not a zero split. A
sprint with `filed` events in which the crew filed nothing reads the zero
crew counts (`crew_total` 0, and all four crew buckets 0) beside the Sponsor,
operator and other counts — a real answer, distinct from null. A sprint with
no events at all reads `filed` null, exactly like its other answers.

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
