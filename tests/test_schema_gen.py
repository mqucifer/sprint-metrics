"""Tests for the JSON Schema file generation in _docs_gen."""

import json

from sprint_metrics._docs_gen import _generate_schema_files


def test_generate_schemas_produces_four_files_with_schema_key(tmp_path):
    """AC1: generating schemas produces four files each with $schema = draft 2020-12."""
    _generate_schema_files(tmp_path)

    filenames = [
        "single-sprint.json",
        "sprint-range.json",
        "trend.json",
        "event-intake.json",
    ]
    for filename in filenames:
        path = tmp_path / filename
        assert path.exists(), f"{filename} was not created"
        data = json.loads(path.read_text())
        assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_single_sprint_schema_required_and_cycle_time(tmp_path):
    """AC2: single-sprint.json required has exactly 11 entries and cycle_time_days accepts [integer, null]."""
    _generate_schema_files(tmp_path)
    data = json.loads((tmp_path / "single-sprint.json").read_text())

    expected_required = [
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
        "flags",
    ]
    assert data["required"] == expected_required
    assert data["properties"]["cycle_time_days"] == {"type": ["integer", "null"]}


def test_event_intake_schema_type_enum_and_required(tmp_path):
    """AC3: event-intake.json type enum has 6 values in order and required has 6 entries."""
    _generate_schema_files(tmp_path)
    data = json.loads((tmp_path / "event-intake.json").read_text())

    assert data["properties"]["type"]["enum"] == [
        "started",
        "blocked",
        "unblocked",
        "finished",
        "escalated",
        "attempt_failed",
    ]
    for key in ("api_version", "card_id", "type", "timestamp", "sprint", "card"):
        assert key in data["required"]


def test_no_schema_file_contains_ref(tmp_path):
    """AC4: none of the four schema files contain the substring $ref."""
    _generate_schema_files(tmp_path)

    for filename in ("single-sprint.json", "sprint-range.json", "trend.json", "event-intake.json"):
        content = (tmp_path / filename).read_text()
        assert "$ref" not in content, f"{filename} contains $ref"


def test_regeneration_updates_only_changed_schema(tmp_path):
    """AC5: after adding a property to TREND_SCHEMA, re-generation updates trend.json
    and leaves the other three files byte-identical."""
    from sprint_metrics.schema import TREND_SCHEMA

    _generate_schema_files(tmp_path)
    before = {
        name: (tmp_path / name).read_bytes()
        for name in ("single-sprint.json", "sprint-range.json", "trend.json", "event-intake.json")
    }

    try:
        TREND_SCHEMA["properties"]["direction"] = {"type": "string"}
        _generate_schema_files(tmp_path)
    finally:
        del TREND_SCHEMA["properties"]["direction"]

    trend_data = json.loads((tmp_path / "trend.json").read_text())
    assert trend_data["properties"]["direction"] == {"type": "string"}
    assert (tmp_path / "single-sprint.json").read_bytes() == before["single-sprint.json"]
    assert (tmp_path / "sprint-range.json").read_bytes() == before["sprint-range.json"]
    assert (tmp_path / "event-intake.json").read_bytes() == before["event-intake.json"]
