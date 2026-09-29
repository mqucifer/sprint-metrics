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
