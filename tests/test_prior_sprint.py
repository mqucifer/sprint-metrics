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


def test_prior_sprint_markdown_shows_prior_values_and_change(tmp_path, capsys):
    """AC1: sprint 2024-01 has 3 completed cards (created 2023-12-31, started
    2024-01-02, completed 2024-01-08) and sprint 2024-02 has 5 completed cards
    (created 2024-01-01, started 2024-01-03, completed 2024-01-07). Running with
    --prior-sprint 2024-01 and --markdown shows the prior values and signed
    change for cycle time, lead time, and throughput."""
    prior_card = {"created": "2023-12-31", "started": "2024-01-02", "completed": "2024-01-08"}
    current_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [prior_card] * 3, "2024-02": [current_card] * 5}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days (was 6 days, -2)" in captured.out
    assert "- **Lead time**: 6 days (was 8 days, -2)" in captured.out
    assert "- **Throughput**: 5 (was 3, +2)" in captured.out


def test_markdown_without_prior_sprint_has_no_was(tmp_path, capsys):
    """AC2: a JSON list with one completed card, run with --markdown and without
    --prior-sprint, shows cycle time without the substring 'was' anywhere."""
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([COMPLETED_CARD]))
    exit_code = main([str(path), "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days" in captured.out
    assert "was" not in captured.out


def test_prior_sprint_in_flight_card_shows_zero_cycle_time(tmp_path, capsys):
    """AC3: sprint 2024-01 has one in-flight card (created 2024-01-01, started
    2024-01-02, no completed date) and sprint 2024-02 has one completed card
    (created 2024-01-01, started 2024-01-03, completed 2024-01-07). Running with
    --prior-sprint 2024-01 and --markdown shows cycle time 4 days (was 0 days, +4)
    and escalation rate 0% (was 0%, 0)."""
    in_flight = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}
    sprints = {"2024-01": [in_flight], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days (was 0 days, +4)" in captured.out
    assert "- **Escalation rate**: 0% (was 0%, 0)" in captured.out


def test_prior_sprint_identical_dates_show_zero_change(tmp_path, capsys):
    """AC4: both sprints have one completed card with identical dates. Running
    with --prior-sprint 2024-01 and --markdown shows cycle time 4 days (was 4
    days, 0) and throughput 1 (was 1, 0)."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days (was 4 days, 0)" in captured.out
    assert "- **Throughput**: 1 (was 1, 0)" in captured.out


def test_prior_sprint_json_includes_prior_and_delta(tmp_path, capsys):
    """AC1: a JSON object with sprint 2024-01 (one card, cycle 4, lead 6) and
    sprint 2024-02 (one card, cycle 5, lead 7), run with --prior-sprint 2024-01
    and --json, exits 0 and the JSON output includes a prior object with the
    prior sprint's six metrics and a delta object with the signed change."""
    prior_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    current_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-08"}
    sprints = {"2024-01": [prior_card], "2024-02": [current_card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["prior"]["cycle_time_days"] == 4
    assert data["prior"]["lead_time_days"] == 6
    assert data["prior"]["throughput"] == 1
    assert data["prior"]["wip_violations"] == 0
    assert data["prior"]["blocked_aging_days"] == 0
    assert data["prior"]["escalation_rate_percent"] == 0
    assert data["delta"]["cycle_time_days"] == 1
    assert data["delta"]["lead_time_days"] == 1
    assert data["delta"]["throughput"] == 0
    assert data["delta"]["wip_violations"] == 0
    assert data["delta"]["blocked_aging_days"] == 0
    assert data["delta"]["escalation_rate_percent"] == 0


def test_prior_sprint_json_top_level_metrics_from_most_recent(tmp_path, capsys):
    """AC2: the top-level metrics are computed from the most recent sprint label
    (2024-02), and the response includes api_version "1"."""
    prior_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    current_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-08"}
    sprints = {"2024-01": [prior_card], "2024-02": [current_card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["api_version"] == "1"
    assert data["cycle_time_days"] == 5
    assert data["lead_time_days"] == 7
    assert data["throughput"] == 1
    assert data["wip_violations"] == 0
    assert data["blocked_aging_days"] == 0
    assert data["escalation_rate_percent"] == 0


def test_prior_sprint_json_missing_sprint_exits_2(tmp_path, capsys):
    """AC3: a JSON object containing only sprint 2024-02, run with
    --prior-sprint 2024-01 and --json, exits 2, stderr contains the string
    2024-01, and stdout is empty."""
    sprints = {"2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "2024-01" in captured.err
    assert captured.out == ""
