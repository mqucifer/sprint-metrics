"""Tests for the --schema flag on the sprint-metrics command."""

import json

import jsonschema
import pytest

from sprint_metrics import main
from sprint_metrics.schema import EVENT_INTAKE_SCHEMA, SINGLE_SPRINT_SCHEMA, SPRINT_RANGE_SCHEMA


def test_schema_json_single_sprint(capsys):
    """AC1: --schema --json without a cards file exits 0 and stdout is a valid
    JSON Schema (draft 2020-12) whose required array includes all eight keys
    and whose metric properties accept null."""
    exit_code = main(["--schema", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    schema = json.loads(captured.out)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for key in (
        "api_version",
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
        "flags",
    ):
        assert key in schema["required"]
    for key in (
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
        "first_attempt_rate_percent",
    ):
        assert schema["properties"][key]["type"] == ["integer", "null"]


def test_schema_json_sprint_range(capsys):
    """AC2: --schema --sprint-range 2024-01..2024-02 --json exits 0 and stdout is a
    JSON Schema whose top-level required includes api_version and sprints, and each
    sprint value's schema includes the six metric keys, flags, prior, and delta,
    with metric types accepting null."""
    exit_code = main(["--schema", "--sprint-range", "2024-01..2024-02", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    schema = json.loads(captured.out)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "api_version" in schema["required"]
    assert "sprints" in schema["required"]
    sprint_schema = schema["properties"]["sprints"]["additionalProperties"]
    for key in (
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
        "flags",
        "prior",
        "delta",
    ):
        assert key in sprint_schema["required"]
    for key in (
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
        "first_attempt_rate_percent",
    ):
        assert sprint_schema["properties"][key]["type"] == ["integer", "null"]


def test_schema_markdown_exits_2(capsys):
    """AC3: --schema --markdown exits 2, stderr contains a message explaining that
    --schema is only valid with --json, and stdout is empty."""
    exit_code = main(["--schema", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--json" in captured.err
    assert captured.out == ""


def test_schema_json_required_keys_and_properties(capsys):
    """AC2: --schema --json exits 0; stdout is JSON whose required array contains
    the named keys and whose properties include cycle_time_days typed as [integer, null]."""
    exit_code = main(["--schema", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    schema = json.loads(captured.out)
    for key in (
        "api_version",
        "cycle_time_days",
        "throughput",
        "first_attempt_rate_percent",
        "failure_breakdown",
        "flags",
        "points_delivered",
        "first_attempt_numerator",
        "first_attempt_denominator",
        "escalation_count",
    ):
        assert key in schema["required"]
    assert schema["properties"]["cycle_time_days"] == {"type": ["integer", "null"]}
    for key in (
        "points_delivered",
        "first_attempt_numerator",
        "first_attempt_denominator",
        "escalation_count",
    ):
        assert schema["properties"][key] == {"type": ["integer", "null"]}


def test_schema_without_json_exits_2(capsys):
    """AC3: --schema without --json exits 2, stderr contains 'only valid with --json',
    and stdout is empty."""
    exit_code = main(["--schema"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "only valid with --json" in captured.err
    assert captured.out == ""


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


def test_single_sprint_json_output_validates_against_schema(tmp_path, capsys):
    """AC1: CLI JSON output for a completed card validates against SINGLE_SPRINT_SCHEMA
    and api_version is the string '1'."""
    cards = json.dumps(
        [
            {
                "id": "card-1",
                "title": "A card",
                "created": "2024-01-01",
                "started": "2024-01-03",
                "completed": "2024-01-07",
            }
        ]
    )
    cards_file = tmp_path / "cards.json"
    cards_file.write_text(cards)

    exit_code = main([str(cards_file), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    jsonschema.validate(result, SINGLE_SPRINT_SCHEMA)
    assert result["api_version"] == "1"
    assert result["points_delivered"] == 0
    assert result["first_attempt_numerator"] == 1
    assert result["first_attempt_denominator"] == 1
    assert result["escalation_count"] == 0


def test_empty_sprint_json_output_validates_against_schema(tmp_path, capsys):
    """AC2: CLI JSON output for an empty sprint validates against SINGLE_SPRINT_SCHEMA."""
    cards_file = tmp_path / "cards.json"
    cards_file.write_text("[]")

    exit_code = main([str(cards_file), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    jsonschema.validate(result, SINGLE_SPRINT_SCHEMA)


def test_schema_rejects_type_mismatched_throughput(tmp_path, capsys):
    """AC3: A type-mismatched throughput (string instead of int) raises ValidationError."""
    cards = json.dumps(
        [
            {
                "id": "card-1",
                "title": "A card",
                "created": "2024-01-01",
                "started": "2024-01-03",
                "completed": "2024-01-07",
            }
        ]
    )
    cards_file = tmp_path / "cards.json"
    cards_file.write_text(cards)

    exit_code = main([str(cards_file), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    result["throughput"] = "1"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(result, SINGLE_SPRINT_SCHEMA)


def test_sprint_range_json_output_validates_against_schema(tmp_path, capsys):
    """AC1: CLI sprint-range JSON output validates against SPRINT_RANGE_SCHEMA and
    top-level keys are exactly 'api_version' and 'sprints'."""
    completed_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [completed_card], "2024-02": [completed_card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))

    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    jsonschema.validate(result, SPRINT_RANGE_SCHEMA)
    assert set(result.keys()) == {"api_version", "sprints"}


def test_sprint_range_single_sprint_empty_validates_against_schema(tmp_path, capsys):
    """AC2: A single-sprint range with an empty sprint validates against SPRINT_RANGE_SCHEMA."""
    sprints = {"2024-01": []}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))

    exit_code = main([str(path), "--sprint-range", "2024-01..2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    result = json.loads(captured.out)
    jsonschema.validate(result, SPRINT_RANGE_SCHEMA)


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
                "escalation_rate_percent": 0,
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


def test_single_sprint_schema_accepts_valid_non_null_object():
    """AC1: A complete non-null JSON object validates against SINGLE_SPRINT_SCHEMA."""
    from sprint_metrics.schema import SINGLE_SPRINT_SCHEMA

    valid = {
        "api_version": "1",
        "throughput": 1,
        "cycle_time_days": 4,
        "lead_time_days": 6,
        "wip_violations": 0,
        "blocked_aging_days": 0,
        "escalation_rate_percent": 0,
        "points_delivered": 0,
        "first_attempt_numerator": 1,
        "first_attempt_denominator": 1,
        "escalation_count": 0,
        "first_attempt_rate_percent": 100,
        "failure_breakdown": [{"class": "parse", "role": "Developer", "count": 2}],
        "top_failure_causes": [{"class": "parse", "count": 2}],
        "flags": {
            "cycle_time_days": False,
            "lead_time_days": False,
            "throughput": False,
            "wip_violations": False,
            "blocked_aging_days": False,
            "escalation_rate_percent": False,
            "first_attempt_rate_percent": False,
        },
    }
    jsonschema.validate(valid, SINGLE_SPRINT_SCHEMA)


def test_single_sprint_schema_rejects_string_failure_breakdown():
    """AC2: failure_breakdown as a string (not an array) fails validation."""
    from sprint_metrics.schema import SINGLE_SPRINT_SCHEMA

    invalid = {
        "api_version": "1",
        "throughput": 1,
        "cycle_time_days": 4,
        "lead_time_days": 6,
        "wip_violations": 0,
        "blocked_aging_days": 0,
        "escalation_rate_percent": 0,
        "first_attempt_rate_percent": 100,
        "failure_breakdown": "not_an_array",
        "top_failure_causes": {},
        "flags": {
            "cycle_time_days": False,
            "lead_time_days": False,
            "throughput": False,
            "wip_violations": False,
            "blocked_aging_days": False,
            "escalation_rate_percent": False,
            "first_attempt_rate_percent": False,
        },
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(invalid, SINGLE_SPRINT_SCHEMA)
    assert "failure_breakdown" in str(exc_info.value)


def test_single_sprint_schema_accepts_all_null_metrics():
    """AC3: Every metric property accepts null alongside its non-null type."""
    from sprint_metrics.schema import SINGLE_SPRINT_SCHEMA

    all_null = {
        "api_version": "1",
        "throughput": None,
        "cycle_time_days": None,
        "lead_time_days": None,
        "wip_violations": None,
        "blocked_aging_days": None,
        "escalation_rate_percent": None,
        "points_delivered": None,
        "first_attempt_numerator": None,
        "first_attempt_denominator": None,
        "escalation_count": None,
        "first_attempt_rate_percent": None,
        "failure_breakdown": None,
        "top_failure_causes": None,
        "flags": None,
    }
    jsonschema.validate(all_null, SINGLE_SPRINT_SCHEMA)


def test_sprint_range_schema_accepts_all_null_sprint_entry():
    """AC4: The per-sprint object in SPRINT_RANGE_SCHEMA accepts null for every field."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    all_null_sprint = {
        "api_version": "1",
        "sprints": {
            "2026-11": {
                "cycle_time_days": None,
                "lead_time_days": None,
                "throughput": None,
                "wip_violations": None,
                "blocked_aging_days": None,
                "escalation_rate_percent": None,
                "points_delivered": None,
                "first_attempt_numerator": None,
                "first_attempt_denominator": None,
                "escalation_count": None,
                "first_attempt_rate_percent": None,
                "failure_breakdown": None,
                "top_failure_causes": None,
                "flags": None,
                "prior": None,
                "delta": None,
            }
        },
    }
    jsonschema.validate(all_null_sprint, SPRINT_RANGE_SCHEMA)


def test_schema_json_required_includes_four_new_fields_with_integer_null_type(capsys):
    """AC3/AC7: --schema --json produces a schema whose required array has exactly
    15 entries (11 existing + 4 new) and whose properties define each new field
    with type [integer, null]."""
    exit_code = main(["--schema", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    schema = json.loads(captured.out)
    assert len(schema["required"]) == 15
    for key in (
        "points_delivered",
        "first_attempt_numerator",
        "first_attempt_denominator",
        "escalation_count",
    ):
        assert key in schema["required"]
        assert schema["properties"][key] == {"type": ["integer", "null"]}
