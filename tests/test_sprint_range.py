"""Tests for the --sprint-range flag on the sprint-metrics command."""

import json

import pytest

from sprint_metrics import main

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}


@pytest.fixture
def run_range_command(tmp_path, capsys):
    """Run the command with a JSON object of sprint cards and a --sprint-range argument."""

    def run(sprints, sprint_range, wip_limits=None, escalations=0, sprint_date=None):
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
