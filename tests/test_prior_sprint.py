"""Tests for the --prior-sprint flag on the sprint-metrics command."""

import json

from sprint_metrics import main

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}


def test_prior_sprint_markdown_includes_prior_sprint_metrics(tmp_path, capsys):
    """AC1: a JSON object with sprint labels 2024-01 and 2024-02, each with one
    completed card, run with --prior-sprint 2024-01 and --markdown, exits 0 and
    the markdown output includes the prior sprint's cycle time, lead time,
    throughput, WIP violations, blocked aging, and escalation rate."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "## Prior Sprint 2024-01" in captured.out
    assert "- **Cycle time**: 4 days" in captured.out
    assert "- **Lead time**: 6 days" in captured.out
    assert "- **Throughput**: 1 cards" in captured.out
    assert "- **WIP violations**: 0" in captured.out
    assert "- **Blocked aging**: 0 days" in captured.out
    assert "- **Escalation rate**: 0%" in captured.out


def test_prior_sprint_missing_sprint_exits_2(tmp_path, capsys):
    """AC2: a JSON object with only sprint label 2024-02, run with
    --prior-sprint 2024-01 and --markdown, exits 2, writes an error to stderr
    that includes the string 2024-01, and writes nothing to stdout."""
    sprints = {"2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "2024-01" in captured.err
    assert captured.out == ""


def test_prior_sprint_json_list_rejected(tmp_path, capsys):
    """AC3: a JSON list of cards, run with --prior-sprint 2024-01 and --markdown,
    exits 2, writes an error to stderr that explains the cards file must be a
    JSON object keyed by sprint label, and writes nothing to stdout."""
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([COMPLETED_CARD]))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "JSON object" in captured.err
    assert "sprint label" in captured.err
    assert captured.out == ""


def test_prior_sprint_cannot_be_most_recent(tmp_path, capsys):
    """AC4: a JSON object with sprint labels 2024-01 and 2024-02, run with
    --prior-sprint 2024-02 and --markdown, exits 2, writes an error to stderr
    indicating that the prior sprint cannot be the most recent sprint, and
    writes nothing to stdout."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-02", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "most recent" in captured.err
    assert captured.out == ""
