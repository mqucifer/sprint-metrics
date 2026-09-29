"""Tests for the CLI entry point in sprint_metrics.cli."""

import json
import subprocess
import sys

from sprint_metrics.cli import main


def test_main_from_cli_module_reports_completed_card(tmp_path, capsys):
    """AC1: main called from sprint_metrics.cli with a valid cards file returns 0
    and stdout contains the expected table row."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in captured.out


def test_main_from_cli_module_rejects_invalid_json(tmp_path, capsys):
    """AC2: main called from sprint_metrics.cli with invalid JSON and --json returns 2,
    stderr contains 'sprint-metrics', and stdout is empty."""
    path = tmp_path / "bad.json"
    path.write_text("not valid json")
    exit_code = main([str(path), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "sprint-metrics" in captured.err
    assert captured.out == ""


def test_scrape_log_message_uses_all_interfaces(tmp_path):
    """AC1: stdout contains a line starting with 'sprint-metrics: serving metrics at'
    and that line does not contain '127.0.0.1'."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))

    proc = subprocess.Popen(
        [sys.executable, "-m", "sprint_metrics", str(cards_path), "--scrape", "--port", "0"],
        stdout=subprocess.PIPE,
    )
    try:
        line = proc.stdout.readline().decode().strip()
        assert line.startswith("sprint-metrics: serving metrics at")
        assert "127.0.0.1" not in line
    finally:
        proc.kill()
        proc.wait()


def test_table_shows_threshold_flag_on_breached_cell_only(tmp_path, capsys):
    """AC2: A completed card with cycle time 7 days and lead time 7 days, with
    thresholds {"cycle_time_days": 5}, produces a table where the cycle time
    cell has a warning marker but the lead time cell does not."""
    cards = [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"cycle_time_days": 5}))
    exit_code = main([str(cards_path), "--thresholds", str(thresholds_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    lines = [line for line in captured.out.splitlines() if line.startswith("| Current")]
    assert lines, "no Current row found"
    cells = [c.strip() for c in lines[0].split("|")[1:-1]]
    assert "7 days" in cells[1]
    assert "\u26a0\ufe0f" in cells[1]
    assert "7 days" in cells[2]
    assert "\u26a0\ufe0f" not in cells[2]


def test_command_reports_json_error_for_invalid_thresholds_json(tmp_path, capsys):
    """AC3: A thresholds file with invalid JSON, invoked with --json and
    --thresholds, exits 2, stderr contains 'sprint-metrics', stdout is empty."""
    cards = [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text("not valid json")
    exit_code = main([str(cards_path), "--json", "--thresholds", str(thresholds_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "sprint-metrics" in captured.err
    assert captured.out == ""
