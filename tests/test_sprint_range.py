"""Tests for the --sprint-range flag on the sprint-metrics command."""

import json

import pytest

from sprint_metrics import main

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}


@pytest.fixture
def run_range_command(tmp_path, capsys):
    """Run the command with a JSON object of sprint cards and a --sprint-range argument."""

    def run(
        sprints,
        sprint_range,
        wip_limits=None,
        escalations=0,
        sprint_date=None,
        json_output=False,
        markdown=False,
    ):
        path = tmp_path / "sprints.json"
        path.write_text(json.dumps(sprints))
        argv = [str(path), "--sprint-range", sprint_range]
        if wip_limits is not None:
            limits_path = tmp_path / "wip-limits.json"
            limits_path.write_text(json.dumps(wip_limits))
            argv += ["--wip-limits", str(limits_path)]
        if escalations:
            argv += ["--escalations", str(escalations)]
        if sprint_date is not None:
            argv += ["--sprint-date", sprint_date]
        if json_output:
            argv += ["--json"]
        if markdown:
            argv += ["--markdown"]
        exit_code = main(argv)
        captured = capsys.readouterr()
        return exit_code, captured.out, captured.err

    return run


def test_sprint_range_reports_one_row_per_sprint(run_range_command):
    """AC1: a JSON object with keys '2024-01' and '2024-02', each containing one
    completed card, produces two table rows in order when --sprint-range
    2024-01..2024-02 is given, and no row is labelled Current."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    exit_code, output, _ = run_range_command(sprints, "2024-01..2024-02")

    assert exit_code == 0
    assert "| 2024-01 | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in output
    assert "| 2024-02 | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in output
    assert "| Current |" not in output
    # Verify order: 2024-01 row appears before 2024-02 row
    idx_01 = output.index("| 2024-01 |")
    idx_02 = output.index("| 2024-02 |")
    assert idx_01 < idx_02


def test_sprint_range_missing_sprint_exits_2(run_range_command):
    """AC2: when the range includes a sprint label not present in the JSON object,
    the command exits 2, writes an error to stderr naming the missing label, and
    writes nothing to stdout."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    exit_code, output, errors = run_range_command(sprints, "2024-01..2024-03")

    assert exit_code == 2
    assert "2024-03" in errors
    assert output == ""


def test_single_sprint_list_without_range_shows_current(tmp_path, capsys):
    """AC3: a JSON list of cards (the single-sprint format) without --sprint-range
    exits 0 and writes a table that includes a row containing 'Current'."""
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([COMPLETED_CARD]))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| Current |" in captured.out


def test_sprint_range_with_json_list_rejected(tmp_path, capsys):
    """When the cards file is a JSON list and --sprint-range is provided, the
    command exits 2 with an error explaining the format mismatch."""
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([COMPLETED_CARD]))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "JSON object" in captured.err
    assert captured.out == ""


def test_sprint_range_invalid_month_rejected(tmp_path, capsys):
    """A sprint label with month 13 is not a valid YYYY-MM label; the command
    exits 2 with an error naming the invalid label."""
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps({"2024-01": [COMPLETED_CARD]}))
    exit_code = main([str(path), "--sprint-range", "2024-13..2024-01"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "2024-13" in captured.err
    assert captured.out == ""


def test_sprint_range_invalid_format_rejected(tmp_path, capsys):
    """A sprint-range argument that is not START..END is rejected with exit 2."""
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps({"2024-01": [COMPLETED_CARD]}))
    exit_code = main([str(path), "--sprint-range", "2024-01"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""


def test_sprint_range_multi_year(tmp_path, capsys):
    """A range spanning year boundaries produces the correct sequence of labels."""
    sprints = {
        "2023-12": [COMPLETED_CARD],
        "2024-01": [COMPLETED_CARD],
        "2024-02": [COMPLETED_CARD],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2023-12..2024-02"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| 2023-12 |" in captured.out
    assert "| 2024-01 |" in captured.out
    assert "| 2024-02 |" in captured.out
    idx_12 = captured.out.index("| 2023-12 |")
    idx_01 = captured.out.index("| 2024-01 |")
    idx_02 = captured.out.index("| 2024-02 |")
    assert idx_12 < idx_01 < idx_02


def test_sprint_range_with_escalations(tmp_path, capsys):
    """The --escalations flag applies to each sprint in the range."""
    sprints = {"2024-01": [COMPLETED_CARD] * 10, "2024-02": [COMPLETED_CARD] * 10}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02", "--escalations", "2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| 2024-01 | 4 days | 6 days | 10 | 0 | 0 days | 20% |" in captured.out
    assert "| 2024-02 | 4 days | 6 days | 10 | 0 | 0 days | 20% |" in captured.out


def test_sprint_range_with_wip_limits(tmp_path, capsys):
    """WIP limits apply to each sprint in the range."""
    in_flight = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}
    sprints = {"2024-01": [in_flight] * 4, "2024-02": [in_flight] * 4}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    limits_path = tmp_path / "wip-limits.json"
    limits_path.write_text(json.dumps({"In Progress": 3}))
    exit_code = main(
        [str(path), "--sprint-range", "2024-01..2024-02", "--wip-limits", str(limits_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| 2024-01 | 0 days | 0 days | 0 | 1 | 0 days | 0% |" in captured.out
    assert "| 2024-02 | 0 days | 0 days | 0 | 1 | 0 days | 0% |" in captured.out


def test_sprint_range_with_sprint_date(tmp_path, capsys):
    """The --sprint-date flag applies to blocked aging for each sprint in the range."""
    sprints = {
        "2024-01": [
            {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
            {"created": "2024-01-01", "blocked_since": "2024-01-02"},
        ],
        "2024-02": [
            {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
            {"created": "2024-01-01", "blocked_since": "2024-01-02"},
        ],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main(
        [str(path), "--sprint-range", "2024-01..2024-02", "--sprint-date", "2024-01-31"]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| 2024-01 | 4 days | 6 days | 1 | 0 | 29 days | 0% |" in captured.out
    assert "| 2024-02 | 4 days | 6 days | 1 | 0 | 29 days | 0% |" in captured.out


def test_sprint_range_with_wip_limits_and_escalations(tmp_path, capsys):
    """AC1: WIP limits and escalations apply to each sprint in the range."""
    in_flight = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}
    completed = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {
        "2024-01": [in_flight] * 4 + [completed] * 2,
        "2024-02": [in_flight] * 4 + [completed] * 2,
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    limits_path = tmp_path / "wip-limits.json"
    limits_path.write_text(json.dumps({"In Progress": 3}))
    exit_code = main(
        [
            str(path),
            "--sprint-range",
            "2024-01..2024-02",
            "--wip-limits",
            str(limits_path),
            "--escalations",
            "1",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| 2024-01 | 4 days | 6 days | 2 | 1 | 0 days | 50% |" in captured.out
    assert "| 2024-02 | 4 days | 6 days | 2 | 1 | 0 days | 50% |" in captured.out


def test_sprint_range_without_wip_limits_or_escalations(tmp_path, capsys):
    """AC2: without --wip-limits and --escalations, each sprint shows 0 violations and 0% escalation."""
    in_flight = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}
    completed = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {
        "2024-01": [in_flight] * 4 + [completed] * 2,
        "2024-02": [in_flight] * 4 + [completed] * 2,
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| 2024-01 | 4 days | 6 days | 2 | 0 | 0 days | 0% |" in captured.out
    assert "| 2024-02 | 4 days | 6 days | 2 | 0 | 0 days | 0% |" in captured.out


def test_sprint_range_with_invalid_wip_limits_format(tmp_path, capsys):
    """AC3: a WIP limits file containing a JSON array is rejected with exit code 2."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    limits_path = tmp_path / "wip-limits.json"
    limits_path.write_text(json.dumps(["In Progress", 3]))
    exit_code = main(
        [str(path), "--sprint-range", "2024-01..2024-02", "--wip-limits", str(limits_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.err
    assert captured.out == ""


def test_sprint_range_json_reports_metrics_per_sprint(run_range_command):
    """AC1: a JSON object with keys '2024-01' and '2024-02', each containing one
    completed card, produces a JSON object keyed by sprint label when --sprint-range
    2024-01..2024-02 and --json are given. Each value has the six metrics."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    exit_code, output, _ = run_range_command(sprints, "2024-01..2024-02", json_output=True)

    assert exit_code == 0
    data = json.loads(output)
    assert set(data.keys()) == {"2024-01", "2024-02"}
    for label in ("2024-01", "2024-02"):
        assert data[label]["cycle_time_days"] == 4
        assert data[label]["lead_time_days"] == 6
        assert data[label]["throughput"] == 1
        assert data[label]["wip_violations"] == 0
        assert data[label]["blocked_aging_days"] == 0
        assert data[label]["escalation_rate_percent"] == 0


def test_sprint_range_json_missing_sprint_exits_2(tmp_path, capsys):
    """AC2: when the range includes a sprint label not present in the JSON object
    and --json is used, the command exits 2, writes an error to stderr naming the
    missing label, and writes nothing to stdout."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-03", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "2024-03" in captured.err
    assert captured.out == ""


def test_sprint_range_json_invalid_card_date_exits_2(tmp_path, capsys):
    """AC3: when a card's created value is not an ISO-8601 date and --sprint-range
    with --json is used, the command exits 2, writes an error to stderr, and
    writes nothing to stdout."""
    sprints = {"2024-01": [{"created": "not-a-date"}]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.err
    assert captured.out == ""


def test_sprint_range_markdown_reports_one_section_per_sprint(run_range_command):
    """AC1: a JSON object with keys '2024-01' and '2024-02', each containing one
    completed card, produces a markdown report with one section per sprint when
    --sprint-range 2024-01..2024-02 and --markdown are given. The report starts
    with '# Crew Performance Report', includes 'Report date:', shows '## Sprint
    2024-01' before '## Sprint 2024-02', and each section carries the sprint's
    delivery metrics and summary counts."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    exit_code, output, _ = run_range_command(sprints, "2024-01..2024-02", markdown=True)

    assert exit_code == 0
    assert output.startswith("# Crew Performance Report")
    assert "Report date:" in output
    idx_01 = output.index("## Sprint 2024-01")
    idx_02 = output.index("## Sprint 2024-02")
    assert idx_01 < idx_02
    for label in ("2024-01", "2024-02"):
        section = output[idx_01:] if label == "2024-01" else output[idx_02:]
        assert f"## Sprint {label}" in section
        assert "- **Cycle time**: 4 days" in section
        assert "- **Lead time**: 6 days" in section
        assert "- **Throughput**: 1 cards" in section
        assert "- **WIP violations**: 0" in section
        assert "- **Blocked aging**: 0 days" in section
        assert "- **Escalation rate**: 0%" in section
        assert "- **Completed**: 1" in section
        assert "- **In progress**: 0" in section
        assert "- **Blocked**: 0" in section


def test_sprint_range_markdown_missing_sprint_exits_2(run_range_command):
    """AC2: when the range includes a sprint label not present in the JSON object
    and --markdown is used, the command exits 2, writes an error to stderr naming
    the missing label, and writes nothing to stdout."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    exit_code, output, errors = run_range_command(sprints, "2024-01..2024-03", markdown=True)

    assert exit_code == 2
    assert "2024-03" in errors
    assert output == ""


def test_sprint_range_markdown_empty_sprint_shows_no_data(run_range_command):
    """AC3: a sprint with no cards shows 'No performance data available' and zero
    summary counts, while a sprint with cards shows its delivery metrics."""
    sprints = {"2024-01": [], "2024-02": [COMPLETED_CARD]}
    exit_code, output, _ = run_range_command(sprints, "2024-01..2024-02", markdown=True)

    assert exit_code == 0
    idx_01 = output.index("## Sprint 2024-01")
    idx_02 = output.index("## Sprint 2024-02")
    assert idx_01 < idx_02
    section_01 = output[idx_01:idx_02]
    assert "No performance data available" in section_01
    assert "- **Completed**: 0" in section_01
    assert "- **Cycle time**" not in section_01
    section_02 = output[idx_02:]
    assert "- **Cycle time**: 4 days" in section_02


def test_sprint_range_json_flags_cycle_time_breached(tmp_path, capsys):
    """AC1: sprint 2024-01 has a card with cycle time 7 days (exceeds threshold of 5)
    and sprint 2024-02 has a card with cycle time 4 days (does not exceed threshold).
    Running with --sprint-range 2024-01..2024-02 --json produces flags where
    cycle_time_days is true for 2024-01 and false for 2024-02, and both sprints
    include all six flag keys."""
    sprints = {
        "2024-01": [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}],
        "2024-02": [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["2024-01"]["flags"]["cycle_time_days"] is True
    assert data["2024-02"]["flags"]["cycle_time_days"] is False
    for label in ("2024-01", "2024-02"):
        flags = data[label]["flags"]
        assert set(flags.keys()) == {
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "escalation_rate_percent",
        }


def test_sprint_range_json_flags_empty_sprint(tmp_path, capsys):
    """AC2: sprint 2024-01 has no cards (empty list) and sprint 2024-02 has one
    completed card with cycle time 4 days. Running with --sprint-range
    2024-01..2024-02 --json produces flags where throughput is true for 2024-01
    (zero completed cards) and all other flags are false, and all six flags are
    false for 2024-02."""
    sprints = {"2024-01": [], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["2024-01"]["flags"]["throughput"] is True
    assert data["2024-01"]["flags"]["cycle_time_days"] is False
    assert data["2024-01"]["flags"]["lead_time_days"] is False
    assert data["2024-01"]["flags"]["wip_violations"] is False
    assert data["2024-01"]["flags"]["blocked_aging_days"] is False
    assert data["2024-01"]["flags"]["escalation_rate_percent"] is False
    for key in (
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
    ):
        assert data["2024-02"]["flags"][key] is False


def test_sprint_range_json_flags_with_user_thresholds(tmp_path, capsys):
    """AC3: both sprints have a card with cycle time 4 days, and a thresholds file
    sets cycle_time_days to 3. Running with --sprint-range 2024-01..2024-02 --json
    --thresholds thresholds.json produces flags where cycle_time_days is true for
    both sprints, confirming user-defined thresholds apply to every sprint in the
    range."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"cycle_time_days": 3}))
    exit_code = main(
        [
            str(path),
            "--sprint-range",
            "2024-01..2024-02",
            "--json",
            "--thresholds",
            str(thresholds_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["2024-01"]["flags"]["cycle_time_days"] is True
    assert data["2024-02"]["flags"]["cycle_time_days"] is True


def test_sprint_range_json_includes_prior_period_metrics(tmp_path, capsys):
    """AC1: a sprints JSON object with keys 2024-01 and 2024-02, where 2024-01 contains
    one completed card created 2024-01-01, started 2024-01-03, completed 2024-01-07,
    and 2024-02 contains one completed card created 2024-01-01, started 2024-01-02,
    completed 2024-01-08. When the command is run with --sprint-range 2024-01..2024-02
    and --json, the exit code is 0 and stdout JSON has 2024-01.prior null,
    2024-02.prior cycle_time_days 4, lead_time_days 6, throughput 1, wip_violations 0,
    blocked_aging_days 0, escalation_rate_percent 0, and both sprint objects still
    contain their own six metric keys."""
    sprints = {
        "2024-01": [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}],
        "2024-02": [{"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-08"}],
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-02", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["2024-01"]["prior"] is None
    assert data["2024-02"]["prior"]["cycle_time_days"] == 4
    assert data["2024-02"]["prior"]["lead_time_days"] == 6
    assert data["2024-02"]["prior"]["throughput"] == 1
    assert data["2024-02"]["prior"]["wip_violations"] == 0
    assert data["2024-02"]["prior"]["blocked_aging_days"] == 0
    assert data["2024-02"]["prior"]["escalation_rate_percent"] == 0
    for label in ("2024-01", "2024-02"):
        for key in (
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "escalation_rate_percent",
        ):
            assert key in data[label]


def test_sprint_range_json_prior_period_wip_and_escalation(tmp_path, capsys):
    """AC2: a sprints JSON object with keys 2024-01 and 2024-02, where 2024-01 contains
    four in-progress cards and ten completed cards, 2024-02 contains two in-progress
    cards and ten completed cards, a WIP limits input with In Progress set to 3, and
    two escalations. When the command is run with --sprint-range 2024-01..2024-02,
    --wip-limits, --escalations 2, and --json, the exit code is 0 and stdout JSON has
    2024-01.wip_violations 1, 2024-02.prior.wip_violations 1, and
    2024-02.prior.escalation_rate_percent 20."""
    in_progress = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}
    completed = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    sprints = {
        "2024-01": [in_progress] * 4 + [completed] * 10,
        "2024-02": [in_progress] * 2 + [completed] * 10,
    }
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    limits_path = tmp_path / "wip-limits.json"
    limits_path.write_text(json.dumps({"In Progress": 3}))
    exit_code = main(
        [
            str(path),
            "--sprint-range",
            "2024-01..2024-02",
            "--wip-limits",
            str(limits_path),
            "--escalations",
            "2",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["2024-01"]["wip_violations"] == 1
    assert data["2024-02"]["prior"]["wip_violations"] == 1
    assert data["2024-02"]["prior"]["escalation_rate_percent"] == 20


def test_sprint_range_json_single_sprint_prior_is_null(tmp_path, capsys):
    """AC3: a sprints JSON object with key 2024-01 containing one completed card.
    When the command is run with --sprint-range 2024-01..2024-01 and --json,
    the exit code is 0 and stdout JSON has 2024-01.prior null."""
    sprints = {"2024-01": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-01", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["2024-01"]["prior"] is None


def test_sprint_range_json_missing_sprint_in_range_exits_2(tmp_path, capsys):
    """AC4: a sprints JSON object with keys 2024-01 and 2024-02. When the command is
    run with --sprint-range 2024-01..2024-03 and --json, the exit code is 2, stderr
    contains 2024-03, and stdout is empty."""
    sprints = {"2024-01": [COMPLETED_CARD], "2024-02": [COMPLETED_CARD]}
    path = tmp_path / "sprints.json"
    path.write_text(json.dumps(sprints))
    exit_code = main([str(path), "--sprint-range", "2024-01..2024-03", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "2024-03" in captured.err
    assert captured.out == ""
