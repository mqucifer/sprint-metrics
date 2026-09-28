# Output formats

The JSON API response schema is shown below. The `--schema` flag (used with
`--json`) prints this schema to standard output.

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
