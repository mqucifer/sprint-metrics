"""Tests for the JSON Schema file generation in _docs_gen."""

import json

from sprint_metrics._docs_gen import _generate_schema_files


def test_generate_schemas_produces_three_files_with_schema_key(tmp_path):
    """AC1: generating schemas produces exactly three files, each with $schema =
    draft 2020-12; single-sprint.json is no longer written."""
    _generate_schema_files(tmp_path)

    filenames = [
        "sprint-range.json",
        "trend.json",
        "event-intake.json",
    ]
    for filename in filenames:
        path = tmp_path / filename
        assert path.exists(), f"{filename} was not created"
        data = json.loads(path.read_text())
        assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(filenames)


def test_event_intake_schema_type_enum_and_required(tmp_path):
    """AC3: event-intake.json type enum has 7 values in order, and the schema declares
    because (string enum), epic (string), and replaced_by (array of integers, nullable)."""
    _generate_schema_files(tmp_path)
    data = json.loads((tmp_path / "event-intake.json").read_text())

    assert data["properties"]["type"]["enum"] == [
        "started",
        "blocked",
        "unblocked",
        "finished",
        "escalated",
        "attempt_failed",
        "superseded",
    ]
    for key in ("api_version", "card_id", "type", "timestamp", "sprint", "card"):
        assert key in data["required"]

    assert data["properties"]["because"] == {"type": "string", "enum": ["sponsor", "story_problem"]}
    assert data["properties"]["epic"] == {"type": "string"}
    assert data["properties"]["replaced_by"] == {
        "type": ["array", "null"],
        "items": {"type": "integer"},
    }


def test_no_schema_file_contains_ref(tmp_path):
    """AC4: none of the three schema files contain the substring $ref."""
    _generate_schema_files(tmp_path)

    for filename in ("sprint-range.json", "trend.json", "event-intake.json"):
        content = (tmp_path / filename).read_text()
        assert "$ref" not in content, f"{filename} contains $ref"


def test_regeneration_updates_only_changed_schema(tmp_path):
    """AC5: after adding a property to TREND_SCHEMA, re-generation updates trend.json
    and leaves the other two files byte-identical."""
    from sprint_metrics.schema import TREND_SCHEMA

    _generate_schema_files(tmp_path)
    before = {
        name: (tmp_path / name).read_bytes()
        for name in ("sprint-range.json", "trend.json", "event-intake.json")
    }

    try:
        TREND_SCHEMA["properties"]["direction"] = {"type": "string"}
        _generate_schema_files(tmp_path)
    finally:
        del TREND_SCHEMA["properties"]["direction"]

    trend_data = json.loads((tmp_path / "trend.json").read_text())
    assert trend_data["properties"]["direction"] == {"type": "string"}
    assert (tmp_path / "sprint-range.json").read_bytes() == before["sprint-range.json"]
    assert (tmp_path / "event-intake.json").read_bytes() == before["event-intake.json"]
