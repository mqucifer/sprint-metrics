# sprint-metrics

Reports how the crew is performing: cycle time, lead time, throughput per
sprint, WIP-limit violations, blocked-card aging, and escalation rate — as a
table, as JSON, and as markdown for the standup issue.

**This repository is built by agents.** The Sponsor sets the goal; the crew
proposes the epics, writes the stories, implements them, reviews, and merges.
See [mqucifer/crew](https://github.com/mqucifer/crew) for the organization
that builds it, and its `docs/ways-of-working.md` for the rules those agents
follow.

Only the scaffolding here was written by hand — enough that CI is green and the
crew has something to branch from.

## Installation

Requires Python 3.12. No third-party runtime packages are needed — the tool
uses only the standard library.

```
uv pip install git+https://github.com/mqucifer/sprint-metrics.git@v0.1.0
```

After installation the `sprint-metrics` command is available on the PATH.

## Basic usage

```
sprint-metrics cards.json
```

`cards.json` is a JSON file of sprint cards. When no file argument is given,
the tool reads the JSON from standard input and prints the default table.
## Input format (cards.json)

For the default single-sprint invocation, the top-level JSON value in `cards.json` must be an array (list), not an object.

Each card object has one required field:

- `created` — an ISO-8601 date string, e.g. `"2024-01-03"`

and three optional fields, each an ISO-8601 date string or omitted:

- `started`
- `completed`
- `blocked_since`

`created` is the only required field per card.

```json
[
  {
    "created": "2024-01-03",
    "started": "2024-01-05",
    "completed": "2024-01-10",
    "blocked_since": "2024-01-06"
  },
  {
    "created": "2024-01-04"
  }
]
```

An empty JSON array (`[]`) is valid input and produces a report in which every metric is zero.

## Metrics

The six delivery metrics reported by `sprint-metrics` and their precise computations:

**Completed card.** A card is completed when it has a completion date. Cards without a completion date (in-flight cards) are excluded from cycle time, lead time, and throughput calculations.

### Cycle time

The mean (average) of the difference between each completed card's completion date and its start date, expressed in whole days and rounded to the nearest whole day, calculated only over cards that have a completion date.

| Output format | Name |
|---|---|
| Table column | `Cycle time` |
| JSON key | `cycle_time_days` |
| Markdown label | `Cycle time` |
| Prometheus | `sprint_cycle_time_days` |

### Lead time

The mean of (completion date minus creation date) in whole days, calculated over completed cards only.

| Output format | Name |
|---|---|
| Table column | `Lead time` |
| JSON key | `lead_time_days` |
| Markdown label | `Lead time` |
| Prometheus | `sprint_lead_time_days` |

### Throughput

The count of cards with a completion date.

| Output format | Name |
|---|---|
| Table column | `Throughput` |
| JSON key | `throughput` |
| Markdown label | `Throughput` |
| Prometheus | `sprint_throughput_cards` |

### WIP violations

The count of board states in which the maximum number of cards present simultaneously at any point during the sprint exceeded that state's configured limit. Only states with a configured limit can be in violation.

| Output format | Name |
|---|---|
| Table column | `WIP violations` |
| JSON key | `wip_violations` |
| Markdown label | `WIP violations` |
| Prometheus | `sprint_wip_violations` |

### Blocked aging

The maximum days any single card has been blocked.

| Output format | Name |
|---|---|
| Table column | `Blocked aging` |
| JSON key | `blocked_aging_days` |
| Markdown label | `Blocked aging` |
| Prometheus | `sprint_blocked_aging_days` |

### Escalation rate

The number of escalations divided by the number of completed cards, expressed as a whole-number percentage.

| Output format | Name |
|---|---|
| Table column | `Escalation rate` |
| JSON key | `escalation_rate_percent` |
| Markdown label | `Escalation rate` |
| Prometheus | `sprint_escalation_rate_percent` |

## Worked example

Save the following as `cards.json`:

```json
[
  {
    "created": "2024-01-03",
    "started": "2024-01-05",
    "completed": "2024-01-10"
  },
  {
    "created": "2024-01-04",
    "started": "2024-01-08"
  }
]
```

Run:

```
sprint-metrics cards.json
```

The full default-table output:

```
| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate | First attempt | Top causes |
|--------|------------|-----------|------------|----------------|---------------|-----------------|---------------|------------|
| Current | 5 days | 7 days | 1 | 0 | 0 days | 0% | 100% | — |
```

The second card has no `completed` field, so it does not count toward throughput or cycle time. Only the first (completed) card contributes to those averages.

- **Cycle time** and **Lead time** are averages over completed cards only.
- **Throughput** is the count of completed cards.
- **WIP violations** counts configured states whose limit was exceeded.
- **Blocked aging** is the maximum blocked duration in the sprint.
- **Escalation rate** is the percentage derived from the supplied escalation count.
