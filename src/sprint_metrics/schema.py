"""JSON Schema documents for the sprint-metrics API: event intake, sprint range, and trend."""

from __future__ import annotations

METRIC_KEYS = [
    "cycle_time_days",
    "lead_time_days",
    "throughput",
    "wip_violations",
    "blocked_aging_days",
    "points_delivered",
    "first_attempt_numerator",
    "first_attempt_denominator",
    "superseded_count",
    "superseded_points",
]

SPRINT_RANGE_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["api_version", "window", "sprints"],
    "properties": {
        "api_version": {"type": "string"},
        "window": {
            "type": "object",
            "required": ["start", "end", "sprint_count", "no_data"],
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "sprint_count": {"type": "integer"},
                "no_data": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "sprints": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": [
                    *METRIC_KEYS,
                    "first_attempt_rate_percent",
                    "failure_breakdown",
                    "top_failure_causes",
                    "superseded_breakdown",
                    "flags",
                    "prior",
                    "delta",
                    "cycle_time_minutes",
                    "lead_time_minutes",
                ],
                "properties": {
                    **{key: {"type": ["integer", "null"]} for key in METRIC_KEYS},
                    "first_attempt_rate_percent": {"type": ["integer", "null"]},
                    "failure_breakdown": {"type": ["array", "null"]},
                    "top_failure_causes": {"type": ["array", "object", "null"]},
                    "superseded_breakdown": {"type": ["object", "null"]},
                    "flags": {"type": ["object", "null"]},
                    "cycle_time_minutes": {"type": ["integer", "null"]},
                    "lead_time_minutes": {"type": ["integer", "null"]},
                    "story_costs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "card_id": {"type": "string"},
                                "model_minutes": {"type": "integer"},
                                "input_tokens": {"type": "integer"},
                                "cached_input_percent": {"type": "integer"},
                                "output_tokens": {"type": "integer"},
                                "reasoning_output_percent": {"type": "integer"},
                            },
                            "required": [
                                "card_id",
                                "model_minutes",
                                "input_tokens",
                                "cached_input_percent",
                                "output_tokens",
                                "reasoning_output_percent",
                            ],
                        },
                    },
                    "cost": {
                        "type": ["object", "null"],
                        "properties": {
                            "middle": {
                                "type": "object",
                                "properties": {
                                    "model_minutes": {"type": "integer"},
                                    "input_tokens": {"type": "integer"},
                                    "output_tokens": {"type": "integer"},
                                },
                                "required": ["model_minutes", "input_tokens", "output_tokens"],
                            },
                            "total": {
                                "type": "object",
                                "properties": {
                                    "model_minutes": {"type": "integer"},
                                    "input_tokens": {"type": "integer"},
                                    "output_tokens": {"type": "integer"},
                                },
                                "required": ["model_minutes", "input_tokens", "output_tokens"],
                            },
                        },
                        "required": ["middle", "total"],
                    },
                    "rework": {
                        "type": ["object", "null"],
                        "properties": {
                            "started": {"type": "integer"},
                            "sent_backs": {
                                "type": ["array", "null"],
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "card_id": {"type": "string"},
                                        "send_backs": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "step": {"type": ["string", "null"]},
                                                    "reason": {"type": ["string", "null"]},
                                                },
                                                "required": ["step", "reason"],
                                            },
                                        },
                                    },
                                    "required": ["card_id", "send_backs"],
                                },
                            },
                            "qa_returns": {
                                "type": ["array", "null"],
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "card_id": {"type": "string"},
                                        "returns": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "step": {"type": ["string", "null"]},
                                                    "reason": {"type": ["string", "null"]},
                                                },
                                                "required": ["step", "reason"],
                                            },
                                        },
                                    },
                                    "required": ["card_id", "returns"],
                                },
                            },
                            "by_step": {
                                "type": "object",
                                "properties": {
                                    "sent_backs": {
                                        "type": "object",
                                        "additionalProperties": {"type": "integer"},
                                    },
                                    "qa_returns": {
                                        "type": "object",
                                        "additionalProperties": {"type": "integer"},
                                    },
                                },
                            },
                        },
                        "required": ["started", "sent_backs"],
                    },
                    "roster": {
                        "type": ["object", "null"],
                        "properties": {
                            "completed_stories": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "released_epics": {
                                "type": ["array", "null"],
                                "items": {"type": "string"},
                            },
                            "achieved_goals": {
                                "type": ["array", "null"],
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["completed_stories", "released_epics", "achieved_goals"],
                    },
                    "dora": {
                        "type": ["object", "null"],
                        "properties": {
                            "release_frequency": {"type": ["integer", "null"]},
                            "lead_time_days": {"type": ["integer", "null"]},
                        },
                        "required": ["release_frequency", "lead_time_days"],
                    },
                    "working_time": {
                        "type": ["object", "null"],
                        "properties": {
                            "per_step": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "step": {"type": ["string", "null"]},
                                        "minutes": {"type": "integer"},
                                    },
                                    "required": ["step", "minutes"],
                                },
                            },
                            "total": {"type": "integer"},
                        },
                        "required": ["per_step", "total"],
                    },
                    "prior": {
                        "type": ["object", "null"],
                        "properties": {
                            **{key: {"type": ["integer", "null"]} for key in METRIC_KEYS},
                            "first_attempt_rate_percent": {"type": ["integer", "null"]},
                            "superseded_breakdown": {"type": ["object", "null"]},
                            "cycle_time_minutes": {"type": ["integer", "null"]},
                            "lead_time_minutes": {"type": ["integer", "null"]},
                            "model_minutes_middle": {"type": ["integer", "null"]},
                            "model_minutes_total": {"type": ["integer", "null"]},
                            "input_tokens_middle": {"type": ["integer", "null"]},
                            "input_tokens_total": {"type": ["integer", "null"]},
                            "output_tokens_middle": {"type": ["integer", "null"]},
                            "output_tokens_total": {"type": ["integer", "null"]},
                            "working_time_minutes": {"type": ["integer", "null"]},
                        },
                    },
                    "delta": {
                        "type": ["object", "null"],
                        "properties": {
                            **{key: {"type": ["integer", "null"]} for key in METRIC_KEYS},
                            "first_attempt_rate_percent": {"type": ["integer", "null"]},
                            "superseded_breakdown": {"type": ["integer", "null"]},
                            "cycle_time_minutes": {"type": ["integer", "null"]},
                            "lead_time_minutes": {"type": ["integer", "null"]},
                            "model_minutes_middle": {"type": ["integer", "null"]},
                            "model_minutes_total": {"type": ["integer", "null"]},
                            "input_tokens_middle": {"type": ["integer", "null"]},
                            "input_tokens_total": {"type": ["integer", "null"]},
                            "output_tokens_middle": {"type": ["integer", "null"]},
                            "output_tokens_total": {"type": ["integer", "null"]},
                            "working_time_minutes": {"type": ["integer", "null"]},
                        },
                    },
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
                "superseded",
                "returned",
            ],
        },
        "timestamp": {"type": "string", "format": "date-time"},
        "sprint": {"type": "string", "minLength": 1},
        "card": {
            "type": "object",
            "required": ["created"],
            "properties": {
                "created": {"type": "string", "format": "date"},
                "created_at": {"type": "string", "format": "date-time"},
                "attempts": {"type": "integer"},
                "failure_class": {"type": "string"},
                "failure_role": {"type": "string"},
                "points": {"type": "integer"},
                "model_seconds": {"type": "integer", "minimum": 0},
                "input_tokens": {"type": "integer", "minimum": 0},
                "cached_input_tokens": {"type": "integer", "minimum": 0},
                "output_tokens": {"type": "integer", "minimum": 0},
                "reasoning_output_tokens": {"type": "integer", "minimum": 0},
                "model_time_split": {
                    "type": "object",
                    "properties": {
                        "refinement": {"type": "integer", "minimum": 0},
                        "delivery": {"type": "integer", "minimum": 0},
                    },
                    "required": ["refinement", "delivery"],
                },
                "kind": {"type": "string"},
            },
        },
        "attempt_number": {"type": "integer"},
        "failure_class": {"type": "string"},
        "failure_role": {"type": "string"},
        "because": {"type": "string", "enum": ["sponsor", "story_problem"]},
        "epic": {"type": "string"},
        "goal": {"type": "string"},
        "replaced_by": {"type": ["array", "null"], "items": {"type": "integer"}},
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
