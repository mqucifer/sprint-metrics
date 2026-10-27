"""Tests for the JSON schema documents the service publishes."""

import jsonschema
import pytest

from sprint_metrics.schema import EVENT_INTAKE_SCHEMA, SPRINT_RANGE_SCHEMA
from sprint_metrics.verdict import MEASURE_REGISTRY


def test_trend_schema_top_level_structure():
    """AC1: TREND_SCHEMA is a dict with correct $schema, type, and required keys."""
    from sprint_metrics.schema import TREND_SCHEMA

    assert isinstance(TREND_SCHEMA, dict)
    assert TREND_SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert TREND_SCHEMA["type"] == "object"
    assert "api_version" in TREND_SCHEMA["required"]
    # Exactly one additional key beyond api_version
    extra = [k for k in TREND_SCHEMA["required"] if k != "api_version"]
    assert extra == ["values"]


def test_trend_schema_values_items_structure():
    """AC2: values is an array of objects each requiring sprint and value, with value accepting null."""
    from sprint_metrics.schema import TREND_SCHEMA

    values_prop = TREND_SCHEMA["properties"]["values"]
    assert values_prop["type"] == "array"
    items = values_prop["items"]
    assert items["type"] == "object"
    assert items["required"] == ["sprint", "value"]
    assert items["properties"]["value"]["type"] == ["integer", "null"]


def test_trend_schema_properties_types():
    """AC5 (UX): properties include metric/start/end as string and values as array."""
    from sprint_metrics.schema import TREND_SCHEMA

    props = TREND_SCHEMA["properties"]
    assert props["metric"]["type"] == "string"
    assert props["start"]["type"] == "string"
    assert props["end"]["type"] == "string"
    assert props["values"]["type"] == "array"


def test_sprint_range_schema_rejects_sprints_as_array():
    """AC3: A JSON object with 'sprints' as an array (instead of an object keyed by
    sprint label) raises a jsonschema.ValidationError."""
    bad = {
        "api_version": "1",
        "sprints": [
            {
                "cycle_time_days": 4,
                "lead_time_days": 6,
                "throughput": 1,
                "wip_violations": 0,
                "blocked_aging_days": 0,
                "first_attempt_rate_percent": 100,
                "top_failure_causes": {},
                "flags": {},
                "prior": None,
                "delta": None,
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SPRINT_RANGE_SCHEMA)


def test_event_intake_valid_event_passes():
    """AC1: A valid board event passes EVENT_INTAKE_SCHEMA validation without raising."""
    event = {
        "api_version": "1",
        "card_id": "c1",
        "type": "started",
        "timestamp": "2024-01-03T10:00:00Z",
        "sprint": "2024-01",
        "card": {"created": "2024-01-01"},
    }
    jsonschema.validate(event, EVENT_INTAKE_SCHEMA)


def test_event_intake_invalid_type_rejected():
    """AC2: A board event with an invalid type raises ValidationError referencing 'type'."""
    event = {
        "api_version": "1",
        "card_id": "c1",
        "type": "frobnicated",
        "timestamp": "2024-01-03T10:00:00Z",
        "sprint": "2024-01",
        "card": {"created": "2024-01-01"},
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(event, EVENT_INTAKE_SCHEMA)
    assert "type" in str(exc_info.value)


def test_event_intake_missing_card_created_rejected():
    """AC3: A board event whose card lacks 'created' raises ValidationError referencing it."""
    event = {
        "api_version": "1",
        "card_id": "c1",
        "type": "finished",
        "timestamp": "2024-01-10T09:00:00Z",
        "sprint": "2024-01",
        "card": {"started": "2024-01-03", "completed": "2024-01-10"},
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(event, EVENT_INTAKE_SCHEMA)
    assert "created" in str(exc_info.value)


def test_sprint_range_schema_accepts_all_null_sprint_entry():
    """AC4: The per-sprint object in SPRINT_RANGE_SCHEMA accepts null for every field."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    all_null_sprint = {
        "api_version": "1",
        "window": {
            "start": "2026-11",
            "end": "2026-11",
            "sprint_count": 1,
            "no_data": ["2026-11"],
            "verdicts": {measure: None for measure in MEASURE_REGISTRY},
        },
        "sprints": {
            "2026-11": {
                "cycle_time_days": None,
                "lead_time_days": None,
                "throughput": None,
                "wip_violations": None,
                "blocked_aging_days": None,
                "points_delivered": None,
                "first_attempt_numerator": None,
                "first_attempt_denominator": None,
                "superseded_count": None,
                "superseded_points": None,
                "first_attempt_rate_percent": None,
                "failure_breakdown": None,
                "top_failure_causes": None,
                "superseded_breakdown": None,
                "flags": None,
                "prior": None,
                "delta": None,
                "cycle_time_minutes": None,
                "lead_time_minutes": None,
            }
        },
    }
    jsonschema.validate(all_null_sprint, SPRINT_RANGE_SCHEMA)


def test_sprint_range_schema_declares_cost_values_as_optional():
    """AC7: the range schema declares story_costs and cost as optional properties on each
    sprint entry, and the six flat cost names as optional (integer/null) properties on
    prior and delta; none of them appear in the entry's required array."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_schema = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "story_costs" in sprint_schema["properties"]
    assert "cost" in sprint_schema["properties"]
    assert "story_costs" not in sprint_schema["required"]
    assert "cost" not in sprint_schema["required"]
    cost_names = (
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
    )
    prior_props = sprint_schema["properties"]["prior"]["properties"]
    delta_props = sprint_schema["properties"]["delta"]["properties"]
    for name in cost_names:
        assert prior_props[name] == {"type": ["integer", "null"]}
        assert delta_props[name] == {"type": ["integer", "null"]}


def _range_entry(**extra):
    """A minimal valid per-sprint range entry; override via extra keyword arguments."""
    base = {
        "cycle_time_days": 5,
        "lead_time_days": 8,
        "throughput": 3,
        "points_delivered": 10,
        "wip_violations": 0,
        "blocked_aging_days": 0,
        "first_attempt_rate_percent": 100,
        "first_attempt_numerator": 3,
        "first_attempt_denominator": 3,
        "superseded_count": 0,
        "superseded_points": 0,
        "superseded_breakdown": {"sponsor": 0, "story_problem": 0},
        "failure_breakdown": [],
        "top_failure_causes": {},
        "flags": {},
        "cycle_time_minutes": None,
        "lead_time_minutes": None,
    }
    base.update(extra)
    return base


def test_sprint_range_schema_accepts_range_entry_with_cost():
    """AC7: a range entry carrying story_costs, cost, and the six flat cost names on its
    prior and delta validates against SPRINT_RANGE_SCHEMA."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    costed_story = {
        "card_id": "p1",
        "model_minutes": 18,
        "input_tokens": 2500,
        "cached_input_percent": 40,
        "output_tokens": 600,
        "reasoning_output_percent": 17,
    }
    cost = {
        "middle": {"model_minutes": 31, "input_tokens": 4000, "output_tokens": 1200},
        "total": {"model_minutes": 92, "input_tokens": 14500, "output_tokens": 5600},
    }
    prior_cost = {
        "model_minutes_middle": 31,
        "model_minutes_total": 92,
        "input_tokens_middle": 4000,
        "input_tokens_total": 14500,
        "output_tokens_middle": 1200,
        "output_tokens_total": 5600,
    }
    delta_cost = {
        "model_minutes_middle": 43,
        "model_minutes_total": 58,
        "input_tokens_middle": 4000,
        "input_tokens_total": 2300,
        "output_tokens_middle": 1650,
        "output_tokens_total": 500,
    }
    verdicts = {measure: None for measure in MEASURE_REGISTRY}
    verdicts["cycle_time_days"] = {
        "verdict": "flat",
        "first_sprint": "2026-09",
        "last_sprint": "2026-10",
        "first_value": 5,
        "last_value": 5,
        "unit": "days",
        "precision": "whole",
    }
    response = {
        "api_version": "1",
        "window": {
            "start": "2026-09",
            "end": "2026-10",
            "sprint_count": 2,
            "no_data": [],
            "verdicts": verdicts,
        },
        "sprints": {
            "2026-09": _range_entry(story_costs=[costed_story], cost=cost, prior=None, delta=None),
            "2026-10": _range_entry(
                story_costs=[costed_story],
                cost=cost,
                prior={**{"cycle_time_days": 5}, **prior_cost},
                delta={**{"cycle_time_days": 0}, **delta_cost},
            ),
        },
    }
    jsonschema.validate(response, SPRINT_RANGE_SCHEMA)


def test_sprint_range_schema_declares_window_verdicts():
    """AC7: SPRINT_RANGE_SCHEMA declares the window's verdicts object as required,
    with exactly one required entry per registry measure; each entry is an
    object-or-null carrying the seven fields, and the non-scalar items get no
    entry."""
    window_schema = SPRINT_RANGE_SCHEMA["properties"]["window"]
    assert "verdicts" in window_schema["required"]
    verdicts_schema = window_schema["properties"]["verdicts"]
    assert verdicts_schema["type"] == "object"
    assert set(verdicts_schema["required"]) == set(MEASURE_REGISTRY)
    assert set(verdicts_schema["properties"]) == set(MEASURE_REGISTRY)
    entry = verdicts_schema["properties"]["cycle_time_days"]
    assert entry["type"] == ["object", "null"]
    assert entry["required"] == [
        "verdict",
        "first_sprint",
        "last_sprint",
        "first_value",
        "last_value",
        "unit",
        "precision",
    ]
    for non_scalar in (
        "failure_breakdown",
        "top_failure_causes",
        "superseded_breakdown",
        "story_costs",
    ):
        assert non_scalar not in verdicts_schema["properties"]


def test_sprint_range_schema_rejects_window_missing_verdicts():
    """AC7: a range response whose window object omits its verdicts is rejected
    by SPRINT_RANGE_SCHEMA."""
    bad = {
        "api_version": "1",
        "window": {
            "start": "2026-11",
            "end": "2026-11",
            "sprint_count": 1,
            "no_data": [],
        },
        "sprints": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SPRINT_RANGE_SCHEMA)


def test_sprint_range_schema_names_no_escalation_measure():
    """#774 AC4: no required list or property anywhere in the range schema names
    escalation_rate_percent or escalation_count."""
    import json

    text = json.dumps(SPRINT_RANGE_SCHEMA)
    assert "escalation_rate_percent" not in text
    assert "escalation_count" not in text


def test_sprint_range_schema_declares_rework_on_sprint_entry():
    """AC8: the range schema declares a rework key on a sprint entry, shaped as
    the service answers it: an object (or null) with started (integer) and
    sent_backs (array or null) of {card_id, send_backs: [{step, reason}]};
    rework is not required, so a pre-rollout entry may omit it."""
    sprint_schema = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "rework" in sprint_schema["properties"]
    assert "rework" not in sprint_schema["required"]
    rework = sprint_schema["properties"]["rework"]
    assert rework["type"] == ["object", "null"]
    assert rework["required"] == ["started", "sent_backs"]
    assert rework["properties"]["started"]["type"] == "integer"
    sent_backs = rework["properties"]["sent_backs"]
    assert sent_backs["type"] == ["array", "null"]
    item = sent_backs["items"]
    assert item["type"] == "object"
    assert item["required"] == ["card_id", "send_backs"]
    assert item["properties"]["card_id"]["type"] == "string"
    send_back_item = item["properties"]["send_backs"]["items"]
    assert send_back_item["type"] == "object"
    assert send_back_item["required"] == ["step", "reason"]
    assert send_back_item["properties"]["step"]["type"] == ["string", "null"]
    assert send_back_item["properties"]["reason"]["type"] == ["string", "null"]


def test_sprint_range_schema_accepts_rework_answer():
    """AC8: a range entry carrying a rework answer (and one with rework null)
    both validate against SPRINT_RANGE_SCHEMA."""
    rework = {
        "started": 5,
        "sent_backs": [
            {"card_id": "s3", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]},
            {"card_id": "s4", "send_backs": [{"step": "QA", "reason": "blocked_session"}]},
        ],
    }
    response = {
        "api_version": "4",
        "window": {
            "start": "2024-03",
            "end": "2024-04",
            "sprint_count": 2,
            "no_data": [],
            "verdicts": {measure: None for measure in MEASURE_REGISTRY},
        },
        "sprints": {
            "2024-03": _range_entry(rework=rework, prior=None, delta=None),
            "2024-04": _range_entry(rework=None, prior=None, delta=None),
        },
    }
    jsonschema.validate(response, SPRINT_RANGE_SCHEMA)


def test_sprint_range_schema_rework_rejects_malformed_send_back():
    """AC8: a rework answer whose send-back omits its step is rejected."""
    bad = {
        "api_version": "4",
        "sprints": {
            "2024-03": _range_entry(
                rework={"started": 1, "sent_backs": [{"card_id": "s3", "send_backs": [{"reason": "x"}]}]},
                prior=None,
                delta=None,
            )
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SPRINT_RANGE_SCHEMA)
