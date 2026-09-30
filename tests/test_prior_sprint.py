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
    change for cycle time, lead time, and throughput, each with a trend arrow."""
    prior_card = {"created": "2023-12-31", "started": "2024-01-02", "completed": "2024-01-08"}
    current_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [prior_card] * 3, "2024-02": [current_card] * 5}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days \u2193 (was 6 days, -2)" in captured.out
    assert "- **Lead time**: 6 days \u2193 (was 8 days, -2)" in captured.out
    assert "- **Throughput**: 5 cards \u2191 (was 3, +2)" in captured.out


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
    --prior-sprint 2024-01 and --markdown shows cycle time 4 days \u2191 (was 0 days, +4)
    and escalation rate 0% \u2192 (was 0%, 0)."""
    in_flight = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}
    sprints = {"2024-01": [in_flight], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days \u2191 (was 0 days, +4)" in captured.out
    assert "- **Escalation rate**: 0% \u2192 (was 0%, 0)" in captured.out


def test_prior_sprint_identical_dates_show_zero_change(tmp_path, capsys):
    """AC4: both sprints have one completed card with identical dates. Running
    with --prior-sprint 2024-01 and --markdown shows cycle time 4 days \u2192 (was 4
    days, 0) and throughput 1 cards \u2192 (was 1, 0)."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days \u2192 (was 4 days, 0)" in captured.out
    assert "- **Throughput**: 1 cards \u2192 (was 1, 0)" in captured.out


def test_prior_sprint_json_includes_prior_and_delta(tmp_path, capsys):
    """AC4: a JSON object with sprint labels 2024-01 and 2024-02, where 2024-01
    contains one card (created 2024-01-01, started 2024-01-03, completed 2024-01-07)
    and 2024-02 contains one card (created 2024-01-01, started 2024-01-02,
    completed 2024-01-08). Running with --prior-sprint 2024-01 --json exits 0 and
    stdout is a JSON object with api_version "1", the current sprint's metrics,
    a flags object, a "prior" object with the prior sprint's metrics including
    first_attempt_rate_percent and top_failure_causes, and a "delta" object with
    the signed change for each metric including first_attempt_rate_percent."""
    sprints = {
        "2024-01": [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}],
        "2024-02": [{"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-08"}],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["api_version"] == "1"
    assert data["cycle_time_days"] == 6
    assert data["lead_time_days"] == 7
    assert data["throughput"] == 1
    assert data["wip_violations"] == 0
    assert data["blocked_aging_days"] == 0
    assert data["escalation_rate_percent"] == 0
    assert "flags" in data
    assert data["prior"] == {
        "cycle_time_days": 4,
        "lead_time_days": 6,
        "throughput": 1,
        "wip_violations": 0,
        "blocked_aging_days": 0,
        "escalation_rate_percent": 0,
        "first_attempt_rate_percent": 100,
        "top_failure_causes": {},
    }
    assert data["delta"] == {
        "cycle_time_days": 2,
        "lead_time_days": 1,
        "throughput": 0,
        "wip_violations": 0,
        "blocked_aging_days": 0,
        "escalation_rate_percent": 0,
        "first_attempt_rate_percent": 0,
    }


def test_prior_sprint_json_missing_sprint_exits_2(tmp_path, capsys):
    """AC2: a JSON object containing only sprint label 2024-02, run with
    --prior-sprint 2024-01 --json, exits 2, stderr contains 2024-01, and
    stdout is empty."""
    sprints = {"2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "2024-01" in captured.err
    assert captured.out == ""


def test_prior_sprint_json_cannot_be_most_recent(tmp_path, capsys):
    """AC3: a JSON object with sprint labels 2024-01 and 2024-02, each containing
    one completed card, run with --prior-sprint 2024-02 --json, exits 2, stderr
    contains 'most recent', and stdout is empty."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-02", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "most recent" in captured.err
    assert captured.out == ""


def test_prior_sprint_markdown_first_attempt_rate_with_change(tmp_path, capsys):
    """AC1: 2024-01 has 3 completed cards (2 first-attempt, 1 not) and 2024-02 has
    5 completed cards (4 first-attempt, 1 not). --prior-sprint 2024-01 --markdown
    exits 0 and stdout contains '- **First-attempt rate**: 80% \u2191 (was 67%, +13)'."""
    first_attempt = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    not_first = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "bug",
    }
    sprints = {
        "2024-01": [first_attempt, first_attempt, not_first],
        "2024-02": [first_attempt] * 4 + [not_first],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **First-attempt rate**: 80% \u2191 (was 67%, +13)" in captured.out


def test_single_sprint_markdown_first_attempt_rate_no_prior(tmp_path, capsys):
    """AC2: a single-sprint JSON list with one completed card with attempts=1, run
    with --markdown and without --prior-sprint, exits 0 and stdout contains
    '- **First-attempt rate**: 100%' and does not contain the substring 'was'."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([card]))
    exit_code = main([str(path), "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **First-attempt rate**: 100%" in captured.out
    assert "was" not in captured.out


def test_prior_sprint_markdown_first_attempt_rate_empty_prior(tmp_path, capsys):
    """AC3: 2024-01 is an empty list and 2024-02 has one completed card with
    attempts=1. --prior-sprint 2024-01 --markdown exits 0 and stdout contains
    '- **First-attempt rate**: 100% \u2191 (was 0%, +100)'."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [], "2024-02": [card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **First-attempt rate**: 100% \u2191 (was 0%, +100)" in captured.out


def test_prior_sprint_markdown_first_attempt_rate_zero_change(tmp_path, capsys):
    """AC4: 2024-01 and 2024-02 each have one completed card with attempts=2 and
    failure_class='bug'. --prior-sprint 2024-01 --markdown exits 0 and stdout
    contains '- **First-attempt rate**: 0% \u2192 (was 0%, 0)'."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "bug",
    }
    sprints = {"2024-01": [card], "2024-02": [card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **First-attempt rate**: 0% \u2192 (was 0%, 0)" in captured.out


def test_prior_sprint_json_top_level_first_attempt_and_top_causes(tmp_path, capsys):
    """AC1: 2024-01 has 3 completed cards (2 first-attempt, 1 with attempts=2
    failure_class='bug') and 2024-02 has 5 completed cards (4 first-attempt, 1 with
    attempts=2 failure_class='requirement'). --prior-sprint 2024-01 --json exits 0,
    top-level first_attempt_rate_percent is 80, top_failure_causes is {'requirement': 1},
    prior first_attempt_rate_percent is 67, prior top_failure_causes is {'bug': 1},
    and delta first_attempt_rate_percent is 13."""
    first_attempt = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    bug_card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "bug",
    }
    requirement_card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "requirement",
    }
    sprints = {
        "2024-01": [first_attempt, first_attempt, bug_card],
        "2024-02": [first_attempt] * 4 + [requirement_card],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["first_attempt_rate_percent"] == 80
    assert data["top_failure_causes"] == {"requirement": 1}
    assert data["prior"]["first_attempt_rate_percent"] == 67
    assert data["prior"]["top_failure_causes"] == {"bug": 1}
    assert data["delta"]["first_attempt_rate_percent"] == 13


def test_prior_sprint_json_delta_zero_when_identical_first_attempt(tmp_path, capsys):
    """AC3: 2024-01 and 2024-02 each have one completed card with attempts=1.
    --prior-sprint 2024-01 --json exits 0, delta first_attempt_rate_percent is 0,
    and prior first_attempt_rate_percent is 100."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [card], "2024-02": [card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["delta"]["first_attempt_rate_percent"] == 0
    assert data["prior"]["first_attempt_rate_percent"] == 100


def test_prior_sprint_markdown_cycle_time_decreased_shows_down_arrow(tmp_path, capsys):
    """AC1: sprint 2024-01 has cycle time 6 days, sprint 2024-02 has cycle time 4 days.
    --prior-sprint 2024-01 --markdown shows the ↓ arrow between the value and the
    open parenthesis on the cycle time line."""
    prior_card = {"created": "2023-12-30", "started": "2024-01-02", "completed": "2024-01-08"}
    current_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [prior_card], "2024-02": [current_card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days \u2193 (was 6 days, -2)" in captured.out


def test_prior_sprint_markdown_throughput_increased_shows_up_arrow(tmp_path, capsys):
    """AC2: prior sprint has 1 completed card, current sprint has 3 completed cards.
    --prior-sprint LABEL --markdown shows the ↑ arrow on the throughput line."""
    sprints = {
        "2024-01": [COMPLETED_CARD],
        "2024-02": [COMPLETED_CARD] * 3,
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Throughput**: 3 cards \u2191 (was 1, +2)" in captured.out


def test_prior_sprint_markdown_cycle_time_unchanged_shows_steady_arrow(tmp_path, capsys):
    """AC3: both sprints have identical cycle time (4 days).
    --prior-sprint LABEL --markdown shows the → arrow on the cycle time line."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days \u2192 (was 4 days, 0)" in captured.out


def test_prior_sprint_markdown_no_prior_shows_no_arrow(tmp_path, capsys):
    """AC4: a single-sprint cards file run with --markdown and no --prior-sprint
    shows cycle time without any arrow character."""
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([COMPLETED_CARD]))
    exit_code = main([str(path), "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days" in captured.out
    assert "\u2193" not in captured.out
    assert "\u2191" not in captured.out
    assert "\u2192" not in captured.out


def test_prior_sprint_markdown_first_attempt_rate_increased_shows_up_arrow(tmp_path, capsys):
    """AC5: prior sprint has 50% first-attempt rate, current sprint has 100%.
    --prior-sprint LABEL --markdown shows the ↑ arrow on the first-attempt rate line."""
    first_attempt = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    not_first = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "bug",
    }
    sprints = {
        "2024-01": [first_attempt, not_first],
        "2024-02": [first_attempt, first_attempt],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **First-attempt rate**: 100% \u2191 (was 50%, +50)" in captured.out


def test_prior_sprint_markdown_arrows_on_all_numeric_metrics(tmp_path, capsys):
    """AC7: all four remaining numeric metrics (lead time, WIP violations, blocked
    aging, escalation rate) show a directional arrow in the Current Sprint section."""
    wip_limits = {"In Progress": 1}
    prior_sprint = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-09"},
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-08"},
        {"created": "2024-01-01", "blocked_since": "2024-02-25"},
    ]
    current_sprint = [
        {"created": "2024-02-01", "started": "2024-02-02", "completed": "2024-02-07"},
        {"created": "2024-02-01", "blocked_since": "2024-02-26"},
    ]
    sprints = {"2024-01": prior_sprint, "2024-02": current_sprint}
    sprints_path = tmp_path / "sprints.json"
    sprints_path.write_text(json.dumps(sprints))
    limits_path = tmp_path / "wip-limits.json"
    limits_path.write_text(json.dumps(wip_limits))
    exit_code = main(
        [
            str(sprints_path),
            "--prior-sprint",
            "2024-01",
            "--markdown",
            "--sprint-date",
            "2024-03-01",
            "--wip-limits",
            str(limits_path),
            "--escalations",
            "1",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "6 days \u2193 (was 8 days" in captured.out
    assert "0 \u2193 (was 1" in captured.out
    assert "4 days \u2193 (was 5 days" in captured.out
    assert "100% \u2191 (was 50%" in captured.out


def test_prior_sprint_markdown_arrows_only_in_current_section(tmp_path, capsys):
    """AC8: the text between '## Prior Sprint' and '## Current Sprint' contains no
    arrow characters, and every metric bullet line between '## Current Sprint' and
    '## Crew Performance Summary' that contains '(was' also contains exactly one
    arrow character."""
    prior_card = {"created": "2023-12-31", "started": "2024-01-02", "completed": "2024-01-08"}
    current_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {"2024-01": [prior_card], "2024-02": [current_card]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--prior-sprint", "2024-01", "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    output = captured.out
    arrows = ("\u2193", "\u2191", "\u2192")

    prior_start = output.index("## Prior Sprint")
    current_start = output.index("## Current Sprint")
    summary_start = output.index("## Crew Performance Summary")

    prior_section = output[prior_start:current_start]
    for arrow in arrows:
        assert arrow not in prior_section, f"arrow {arrow!r} found in Prior Sprint section"

    current_section = output[current_start:summary_start]
    metric_lines = [line for line in current_section.splitlines() if "(was" in line]
    assert metric_lines, "no metric lines with '(was' found in Current Sprint section"
    for line in metric_lines:
        arrow_count = sum(1 for a in arrows if a in line)
        assert arrow_count == 1, f"expected exactly one arrow in {line!r}, found {arrow_count}"
