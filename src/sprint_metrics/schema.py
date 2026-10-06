"""JSON Schema documents for the sprint-metrics API response."""

from __future__ import annotations

METRIC_KEYS = [
    "cycle_time_days",
    "lead_time_days",
    "throughput",
    "wip_violations",
    "blocked_aging_days",
    "escalation_rate_percent",
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
        "cycle_time_days": {"type": "integer"},
        "lead_time_days": {"type": "integer"},
        "throughput": {"type": "integer"},
        "wip_violations": {"type": "integer"},
        "blocked_aging_days": {"type": "integer"},
        "escalation_rate_percent": {"type": "integer"},
        "first_attempt_rate_percent": {"type": "integer"},
        "failure_breakdown": {
            "type": "array",
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
        "top_failure_causes": {"type": "object"},
        "flags": {"type": "object"},
        "sprint_date": {"type": "string"},
        "prior": {
            "type": "object",
            "properties": {
                **{key: {"type": "integer"} for key in METRIC_KEYS},
                "first_attempt_rate_percent": {"type": "integer"},
                "top_failure_causes": {"type": "object"},
            },
        },
        "delta": {
            "type": "object",
            "properties": {
                **{key: {"type": "integer"} for key in METRIC_KEYS},
                "first_attempt_rate_percent": {"type": "integer"},
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
                    "top_failure_causes",
                    "flags",
                    "prior",
                    "delta",
                ],
                "properties": {
                    **{key: {"type": "integer"} for key in METRIC_KEYS},
                    "first_attempt_rate_percent": {"type": "integer"},
                    "top_failure_causes": {"type": "object"},
                    "flags": {"type": "object"},
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
            "enum": ["started", "blocked", "unblocked", "finished", "escalated"],
        },
        "timestamp": {"type": "string", "format": "date-time"},
        "sprint": {"type": "string", "pattern": "^\\d{4}-\\d{2}$"},
        "card": {
            "type": "object",
            "required": ["created"],
            "properties": {
                "created": {"type": "string", "format": "date"},
                "attempts": {"type": "integer"},
                "failure_class": {"type": "string"},
                "failure_role": {"type": "string"},
            },
        },
    },
}
