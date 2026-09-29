"""Tests for the --schema flag on the sprint-metrics command."""

import json

from sprint_metrics import main


def test_schema_json_single_sprint(capsys):
    """AC1: --schema --json without a cards file exits 0 and stdout is a valid
    JSON Schema (draft 2020-12) whose required array includes all eight keys."""
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


def test_schema_json_sprint_range(capsys):
    """AC2: --schema --sprint-range 2024-01..2024-02 --json exits 0 and stdout is a
    JSON Schema whose top-level required includes api_version and sprints, and each
    sprint value's schema includes the six metric keys, flags, prior, and delta."""
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
    the named keys and whose properties include cycle_time_days typed as integer."""
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
    ):
        assert key in schema["required"]
    assert schema["properties"]["cycle_time_days"] == {"type": "integer"}


def test_schema_without_json_exits_2(capsys):
    """AC3: --schema without --json exits 2, stderr contains 'only valid with --json',
    and stdout is empty."""
    exit_code = main(["--schema"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "only valid with --json" in captured.err
    assert captured.out == ""
