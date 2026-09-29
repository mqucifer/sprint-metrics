# Output formats

The JSON API response schema is shown below. The `--schema` flag (used with
`--json`) prints this schema to standard output.

## Single-sprint JSON response

The `--json` flag produces a JSON object with the following top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `api_version` | string | The version of the JSON API format, currently `"1"`. |
| `cycle_time_days` | integer | The average number of days from start to completion across completed cards. |
| `lead_time_days` | integer | The average number of days from creation to completion across completed cards. |
| `throughput` | integer | The number of cards completed during the sprint. |
| `wip_violations` | integer | The number of board states whose WIP limit was exceeded at any point during the sprint. |
| `blocked_aging_days` | integer | The maximum number of days any card has been in a blocked state during the sprint. |
| `escalation_rate_percent` | integer | The percentage of completed cards that were escalated to a higher role. |
| `first_attempt_rate_percent` | integer | The percentage of completed cards that succeeded on the first attempt. |
| `failure_breakdown` | array of `{class, role, count}` objects | The failure causes grouped by class and role, sorted by count descending. |
| `top_failure_causes` | object | A mapping from failure cause (class) to count for the top three causes. |
| `flags` | object | A mapping from metric key to a boolean indicating whether that metric breached its configured threshold. |

### Optional fields

These fields appear only when their corresponding command-line options are used:

| Field | Type | Description |
|-------|------|-------------|
| `sprint_date` | string | The date the sprint was measured, in `YYYY-MM-DD` format. Present when `--sprint-date` is given. |
| `prior` | object | The metrics for the prior period, when `--prior` is given. |
| `delta` | object | The change from the prior period for each numeric metric, when `--prior` is given. |

## Sprint-range JSON response

The sprint-range JSON response (produced when `--sprint-range` is given) is a
top-level object with exactly two keys:

| Field | Type | Description |
|-------|------|-------------|
| `api_version` | string | The version of the JSON API format, currently `"1"`. |
| `sprints` | object | An object keyed by `YYYY-MM` sprint label, where each value is a single-sprint response object. |

Each sprint value carries all the single-sprint fields plus `prior` (object or
null) and `delta` (object or null). For the first sprint in the range, both
`prior` and `delta` are null.

## Scrape endpoints

The scrape server (started with `--serve`) exposes two endpoints:

- **`GET /metrics`** — Prometheus text exposition format, suitable for Prometheus to scrape directly.
- **`GET /json`** — The same JSON object that the `--json` flag writes to standard output.

The cards file is re-read on every request, so board changes appear without a
restart.

## Worked example: empty sprint

Given a cards file containing an empty array:

```json
[]
```

Running:

```
sprint-metrics cards.json --json
```

produces:

```json
{
  "api_version": "1",
  "cycle_time_days": 0,
  "lead_time_days": 0,
  "throughput": 0,
  "wip_violations": 0,
  "blocked_aging_days": 0,
  "escalation_rate_percent": 0,
  "first_attempt_rate_percent": 0,
  "failure_breakdown": [],
  "top_failure_causes": {},
  "flags": {
    "cycle_time_days": false,
    "lead_time_days": false,
    "throughput": true,
    "wip_violations": false,
    "blocked_aging_days": false,
    "escalation_rate_percent": false,
    "first_attempt_rate_percent": true
  }
}
```

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
