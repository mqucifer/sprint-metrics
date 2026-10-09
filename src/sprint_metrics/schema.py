"""JSON Schema documents for the sprint-metrics API response."""

from __future__ import annotations

METRIC_KEYS = [
    "cycle_time_days",
    "lead_time_days",
    "throughput",
    "wip_violations",
    "blocked_aging_days",
    "escalation_rate_percent",
    "points_delivered",
    "first_attempt_numerator",
    "first_attempt_denominator",
    "escalation_count",
]

SINGLE_SPRINT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "api_version",
        *METRIC_KEYS,
        "first_attempt_rate_percent",
        "failure_breakdown",
        "top_failure_causes",
        "flags",
    ],
    "properties": {
        "api_version": {"type": "string"},
        "cycle_time_days": {"type": ["integer", "null"]},
        "lead_time_days": {"type": ["integer", "null"]},
        "throughput": {"type": ["integer", "null"]},
        "wip_violations": {"type": ["integer", "null"]},
        "blocked_aging_days": {"type": ["integer", "null"]},
        "escalation_rate_percent": {"type": ["integer", "null"]},
        "points_delivered": {"type": ["integer", "null"]},
        "first_attempt_numerator": {"type": ["integer", "null"]},
        "first_attempt_denominator": {"type": ["integer", "null"]},
        "escalation_count": {"type": ["integer", "null"]},
        "first_attempt_rate_percent": {"type": ["integer", "null"]},
        "failure_breakdown": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "class": {"type": "string"},
                    "role": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["class", "role", "count"],
            },
        },
        "top_failure_causes": {"type": ["array", "object", "null"]},
        "flags": {"type": ["object", "null"]},
        "sprint_date": {"type": "string"},
        "prior": {
            "type": "object",
            "properties": {
                **{key: {"type": ["integer", "null"]} for key in METRIC_KEYS},
                "first_attempt_rate_percent": {"type": ["integer", "null"]},
                "top_failure_causes": {"type": ["object", "null"]},
            },
        },
        "delta": {
            "type": "object",
            "properties": {
                **{key: {"type": ["integer", "null"]} for key in METRIC_KEYS},
                "first_attempt_rate_percent": {"type": ["integer", "null"]},
            },
        },
    },
}

SPRINT_RANGE_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["api_version", "sprints"],
    "properties": {
        "api_version": {"type": "string"},
        "sprints": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": [
                    *METRIC_KEYS,
                    "first_attempt_rate_percent",
                    "failure_breakdown",
                    "top_failure_causes",
                    "flags",
                    "prior",
                    "delta",
                ],
                "properties": {
                    **{key: {"type": ["integer", "null"]} for key in METRIC_KEYS},
                    "first_attempt_rate_percent": {"type": ["integer", "null"]},
                    "failure_breakdown": {"type": ["array", "null"]},
                    "top_failure_causes": {"type": ["object", "null"]},
                    "flags": {"type": ["object", "null"]},
                    "prior": {"type": ["object", "null"]},
                    "delta": {"type": ["object", "null"]},
                },
            },
        },
    },
}


EVENT_INTAKE_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["api_version", "card_id", "type", "timestamp", "sprint", "card"],
    "properties": {
        "api_version": {"type": "string"},
        "card_id": {"type": "string"},
        "type": {
            "type": "string",
            "enum": [
                "started",
                "blocked",
                "unblocked",
                "finished",
                "escalated",
                "attempt_failed",
            ],
        },
        "timestamp": {"type": "string", "format": "date-time"},
        "sprint": {"type": "string", "minLength": 1},
        "card": {
            "type": "object",
            "required": ["created"],
            "properties": {
                "created": {"type": "string", "format": "date"},
                "attempts": {"type": "integer"},
                "failure_class": {"type": "string"},
                "failure_role": {"type": "string"},
                "points": {"type": "integer"},
            },
        },
        "attempt_number": {"type": "integer"},
        "failure_class": {"type": "string"},
        "failure_role": {"type": "string"},
    },
}


TREND_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["api_version", "values"],
    "properties": {
        "api_version": {"type": "string"},
        "metric": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "values": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["sprint", "value"],
                "properties": {
                    "sprint": {"type": "string"},
                    "value": {"type": ["integer", "null"]},
                },
            },
        },
    },
}
