# Output formats

The JSON response top level carries:

- `api_version` — a string identifying the response shape (currently `"1"`)
- Eight metric fields: `cycle_time_days`, `lead_time_days`, `throughput`, `wip_violations`, `blocked_aging_days`, `escalation_rate_percent`, `first_attempt_rate_percent`, `failure_breakdown`
- `top_failure_causes` — an object mapping failure cause names to their counts
- `flags` — an object of booleans indicating which default thresholds were breached
- `failure_breakdown` — an array of objects, each with `class`, `role`, and `count`
- `sprint_date` (optional) — present when `--sprint-date` is supplied

## API versioning

The `api_version` field in every JSON response identifies the response shape. As long as the tool still reports `api_version` `"1"`, the response shape — fields, types, and their semantics — is unchanged from what you received before the upgrade. No MINOR or PATCH release will alter the response for an existing `api_version`.

A breaking change is the removal of an existing `api_version`. This requires a MAJOR package version bump. The CHANGELOG for that release names the removed version and the replacement. The only way your response shape changes is across a MAJOR boundary that retires the `api_version` you were using.

The full JSON Schema is shown below. The `--schema` flag (used with `--json`)
prints this schema to standard output.

BEGIN:formats
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "api_version",
    "cycle_time_days",
    "lead_time_days",
    "throughput",
    "wip_violations",
    "blocked_aging_days",
    "escalation_rate_percent",
    "first_attempt_rate_percent",
    "failure_breakdown",
    "top_failure_causes",
    "flags"
  ],
  "properties": {
    "api_version": {
      "type": "string"
    },
    "cycle_time_days": {
      "type": "integer"
    },
    "lead_time_days": {
      "type": "integer"
    },
    "throughput": {
      "type": "integer"
    },
    "wip_violations": {
      "type": "integer"
    },
    "blocked_aging_days": {
      "type": "integer"
    },
    "escalation_rate_percent": {
      "type": "integer"
    },
    "first_attempt_rate_percent": {
      "type": "integer"
    },
    "failure_breakdown": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "class": {
            "type": "string"
          },
          "role": {
            "type": "string"
          },
          "count": {
            "type": "integer"
          }
        },
        "required": [
          "class",
          "role",
          "count"
        ]
      }
    },
    "top_failure_causes": {
      "type": "object"
    },
    "flags": {
      "type": "object"
    },
    "sprint_date": {
      "type": "string"
    },
    "prior": {
      "type": "object",
      "properties": {
        "cycle_time_days": {
          "type": "integer"
        },
        "lead_time_days": {
          "type": "integer"
        },
        "throughput": {
          "type": "integer"
        },
        "wip_violations": {
          "type": "integer"
        },
        "blocked_aging_days": {
          "type": "integer"
        },
        "escalation_rate_percent": {
          "type": "integer"
        },
        "first_attempt_rate_percent": {
          "type": "integer"
        },
        "top_failure_causes": {
          "type": "object"
        }
      }
    },
    "delta": {
      "type": "object",
      "properties": {
        "cycle_time_days": {
          "type": "integer"
        },
        "lead_time_days": {
          "type": "integer"
        },
        "throughput": {
          "type": "integer"
        },
        "wip_violations": {
          "type": "integer"
        },
        "blocked_aging_days": {
          "type": "integer"
        },
        "escalation_rate_percent": {
          "type": "integer"
        },
        "first_attempt_rate_percent": {
          "type": "integer"
        }
      }
    }
  }
}
```
END:formats

## Worked examples

The examples below all use the same input to show what each output format produces. The input contains one completed card (created 2024-01-01, started 2024-01-03, completed 2024-01-07) and one in-flight card (created 2024-01-04).

**Input** (`cards.json`):

```json
[
  {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
  {"created": "2024-01-04"}
]
```

### Table

```
sprint-metrics cards.json
```

```
| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate | First attempt | Top causes |
|--------|------------|-----------|------------|----------------|---------------|-----------------|---------------|------------|
| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% | 100% | — |
```

### JSON

```
sprint-metrics cards.json --json
```

```json
{"api_version": "1", "cycle_time_days": 4, "lead_time_days": 6, "throughput": 1, "wip_violations": 0, "blocked_aging_days": 0, "escalation_rate_percent": 0, "first_attempt_rate_percent": 100, "failure_breakdown": [], "top_failure_causes": {}, "flags": {"cycle_time_days": false, "lead_time_days": false, "throughput": false, "wip_violations": false, "blocked_aging_days": false, "escalation_rate_percent": false, "first_attempt_rate_percent": false}}
```

### Markdown

The markdown report begins with a health summary between the report date and the first section heading. When no metric exceeds its threshold, the summary reads `Status: All clear`. When one or more metrics breach, it reads `Status: Attention needed (N metrics breached)` followed by a bulleted list naming each breached metric with its current value and the threshold it exceeded. When a prior sprint is specified with `--prior-sprint`, a `Changed:` line follows the status and any breached-metric bullets, naming the single metric with the largest absolute delta from the prior sprint and whether it improved or worsened. When no prior sprint is provided, no `Changed:` line appears. When one or more cards are blocked or in progress, an `Attention:` line follows, naming the count of blocked cards with the longest block duration and the count of in-progress cards. When the WIP violations count is non-zero and WIP limits are configured, an indented line beneath the WIP violations metric names each breached state, its peak simultaneous occupancy, and the configured limit for that state.

```
sprint-metrics cards.json --markdown
```

```markdown
# Crew Performance Report

Report date: 2024-01-15

Status: All clear

## Current Sprint

- **Cycle time**: 4 days
- **Lead time**: 6 days
- **Throughput**: 1 cards
- **WIP violations**: 0
- **Blocked aging**: 0 days
- **Escalation rate**: 0%
- **First-attempt rate**: 100%

## Crew Performance Summary

- **Completed**: 1
- **In progress**: 0
- **Blocked**: 0
```

> The report date reflects the day the example was captured.

### Prometheus

```
sprint-metrics cards.json --prometheus
```

```
sprint_cycle_time_days 4
sprint_lead_time_days 6
sprint_throughput_cards 1
sprint_wip_violations 0
sprint_blocked_aging_days 0
sprint_escalation_rate_percent 0
sprint_first_attempt_rate_percent 100
```

### Error: invalid input

```
sprint-metrics bad.json --json
```

Exit code: `2`

```
sprint-metrics: Expecting value: line 1 column 1 (char 0)
```

stdout is empty.

## Empty sprint

When the cards file contains an empty array (`[]`), every metric is zero. The
flags for `throughput` and `first_attempt_rate_percent` are `true` because their
values fall below the default thresholds; all other flags are `false`.

**Input** (`cards.json`):

```json
[]
```

### JSON

```
sprint-metrics cards.json --json
```

```json
{"api_version": "1", "cycle_time_days": 0, "lead_time_days": 0, "throughput": 0, "wip_violations": 0, "blocked_aging_days": 0, "escalation_rate_percent": 0, "first_attempt_rate_percent": 0, "failure_breakdown": [], "top_failure_causes": {}, "flags": {"cycle_time_days": false, "lead_time_days": false, "throughput": true, "wip_violations": false, "blocked_aging_days": false, "escalation_rate_percent": false, "first_attempt_rate_percent": true}}
```

## --metrics (metric filtering)

The `--metrics` flag restricts the output to a comma-separated list of metric names. Only the requested metrics appear in the output; all others are omitted.

Valid metric names: `cycle_time_days`, `lead_time_days`, `throughput`, `wip_violations`, `blocked_aging_days`, `escalation_rate_percent`, `first_attempt_rate_percent`, `failure_breakdown`.

**Input** (`cards.json`):

```json
[{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
```

### JSON

Request only throughput and cycle time:

```
sprint-metrics cards.json --json --metrics throughput,cycle_time_days
```

```json
{"api_version": "1", "cycle_time_days": 4, "throughput": 1, "top_failure_causes": {}, "flags": {"cycle_time_days": false, "throughput": false}}
```

### Table

```
sprint-metrics cards.json --metrics throughput,cycle_time_days
```

```
| Sprint | Cycle time | Throughput |
|--------|------------|------------|
| Current | 4 days | 1 |
```

### Error: unknown metric name

```
sprint-metrics cards.json --json --metrics throughput,bogus_metric
```

Exit code: `2`

```
sprint-metrics: unknown metric 'bogus_metric'
```

stdout is empty.
