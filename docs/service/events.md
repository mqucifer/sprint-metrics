# Event intake

Part of the [service reference](../service.md).

The service accepts board and session events via POST /events. The accepted event types are: started, blocked, unblocked, finished, escalated, attempt_failed, superseded, returned, filed, and session. A card's work counts in the sprint where it finishes, wherever it started. The `sprint` field accepts any non-empty string (e.g. 'Sprint 18', 'Q4-2026'); it is not restricted to calendar-month labels.

Every accepted event may carry three optional link fields, which the crew sends on any event type:

- `epic` (top-level, optional string): the story's epic link. Absent when the crew does not know the epic.
- `goal` (top-level, optional string): the story's goal link. Absent when the crew does not know the goal.
- `card.kind` (on the card object, optional string): the story's kind (for example 'story', 'epic', 'goal'). Absent when the crew does not know the kind.

When absent, the stored row holds no data (NULL) for the field. The intake version stays "1".

A `superseded` event marks a card that was replaced by other stories. It carries two fields beyond the common event fields:

- `because` (required): the reason the card was superseded. Accepts the values `"sponsor"` (at the Sponsor's request) or `"story_problem"` (after a story problem).
- `replaced_by` (optional): an array of story identifiers that replaced the card. Absent when the crew does not know the replacements.

No prior event on the card is required for a `superseded` event to be accepted.

A `returned` event marks a story that was handed back to the Business Analyst (for example, from review or QA back to refinement). Beyond the common event fields it carries three fields, all optional:

- `failure_role`: the step or role that sent the story back.
- `failure_class`: the reason the story was sent back.
- `epic`: the story's epic link.

No prior event on the card is required for a `returned` event to be accepted, and re-sending one is as safe as re-sending any other event.

Re-sending an event the service already holds (the same `card_id`, `type`, and `timestamp`) is safe. Fields that are currently NULL in the stored row receive the value supplied by the re-sent event; fields that already hold a value are not changed. You can replay your event log or upgrade your event payload without risking data corruption.

The intake format carries an `api_version` field. The current version is "1". The JSON Schema for the event body is available at GET /schema/event.

A `filed` event reports the per-card filing facts: who filed the card, what opened it, and — for a card filed in another repository, such as a QA Task filed in qa-suite — the project the card is for and counts for. Each is a fact the crew sends, not a count, and each is optional:

- `filer` (top-level, optional string): who filed the card. The crew sends one of the filer-side values: `"crew"` (the crew that builds the service), `"sponsor"` (the Sponsor), `"operator"` (the operator), or `"other"` (anyone else). Absent when the crew does not know who filed the card (in `other`).
- `opener` (top-level, optional string): what opened the card. The crew sends one of the opener kinds: `"found"` (a role found a problem), `"process"` (the crew's own test, release, review, technical epic, or retro), or `"split"` (a split from something already filed). Absent when the card's opener cannot be told apart — the card is then reported as unknown.
- `project` (top-level, optional string): for a card filed in another repository, the project the card is for and counts for (for example `"qa-suite"`). Absent when the card was filed in the same repository as the sprint, or when the crew does not know the project.

When the opener fact is absent, the card is reported as unknown: the opener fact is left out rather than guessed, and the service never infers a bucket from an absent fact.

Card ids are unique within a project. The `project` fact is what tells a card `"123"` filed in one repository apart from the card `"123"` filed in another: the two count as two distinct cards.

Example `filed` event carrying the filing facts:

```json
{
  "api_version": "1",
  "card_id": "42",
  "type": "filed",
  "timestamp": "2024-03-05T09:00:00Z",
  "sprint": "2024-03",
  "card": {
    "created": "2024-03-04"
  },
  "filer": "crew",
  "opener": "process",
  "project": "qa-suite"
}
```

The intake's `api_version` stays "1": the `filed` event is additive. Events without the filing facts are accepted exactly as today, so nothing already sent stops working.

A `session` event records a crew session as what happened: its role, start and end, model time (in seconds), and tokens. For a session, `card_id` and `card` are optional at the envelope level — a session with no card omits both. Its own fields are:

- `role` (top-level, required string): the role the session ran as.
- `start` (top-level, required string, ISO-8601 datetime): the session's start.
- `end` (top-level, required string, ISO-8601 datetime): the session's finish.
- `model_seconds` (top-level, optional integer, minimum 0): model time in seconds.
- `tokens` (top-level, optional integer, minimum 0): total tokens.

A session sent twice (same card, role, start, finish) is held once: re-sending it is safe and no later answer counts it twice. This holds for a card-less session too.

Example `session` event:

```json
{
  "api_version": "1",
  "card_id": "42",
  "type": "session",
  "timestamp": "2024-03-05T10:00:00Z",
  "sprint": "2024-03",
  "card": {
    "created": "2024-03-04"
  },
  "role": "developer",
  "start": "2024-03-05T09:00:00Z",
  "end": "2024-03-05T10:00:00Z",
  "model_seconds": 3600,
  "tokens": 100000
}
```

The intake's `api_version` stays "1": the `session` event is additive. Events without a session are accepted exactly as today, so nothing already sent stops working.

A `finished` event may carry a cost payload on its card object. The cost payload has five fields, each a non-negative integer, and the fields are sent together or not at all — a partial payload is rejected:

- `model_seconds` — total model time across every role's calls for this story
- `input_tokens` — total input tokens consumed
- `cached_input_tokens` — input tokens served from cache
- `output_tokens` — total output tokens produced
- `reasoning_output_tokens` — output tokens spent on reasoning

The cost payload may also carry an optional `model_time_split` sub-object that splits the story's model time between refinement and delivery. Its two fields are each a non-negative integer (model seconds), and the fields are sent together or not at all — a partial sub-object is rejected:

- `refinement` — model seconds spent in refinement
- `delivery` — model seconds spent in delivery

The `model_time_split` sub-object is independent of the five cost fields: a finished event may carry the split without the five fields, or the five fields without the split.

Example cost payload on a finished event's card:

```json
{
  "model_seconds": 3480,
  "input_tokens": 4000,
  "cached_input_tokens": 1800,
  "output_tokens": 900,
  "reasoning_output_tokens": 207,
  "model_time_split": {
    "refinement": 1200,
    "delivery": 2280
  }
}
```
