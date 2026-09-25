"""Tests for threshold flagging in the markdown report."""

import json

from sprint_metrics import main


def test_markdown_flags_cycle_time_when_threshold_breached(tmp_path, capsys):
    """AC1: a card with cycle time 7 days and a thresholds file with cycle_time_days 5
    produces a markdown report where the cycle time line carries a ⚠️ marker."""
    card = {"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"cycle_time_days": 5}))
    exit_code = main([str(cards_path), "--markdown", "--thresholds", str(thresholds_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 7 days ⚠️" in captured.out


def test_markdown_does_not_flag_cycle_time_when_below_threshold(tmp_path, capsys):
    """AC2: a card with cycle time 4 days and a thresholds file with cycle_time_days 5
    produces a markdown report where the cycle time line has no ⚠️ marker."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"cycle_time_days": 5}))
    exit_code = main([str(cards_path), "--markdown", "--thresholds", str(thresholds_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 4 days" in captured.out
    assert "⚠️" not in captured.out


def test_markdown_does_not_flag_cycle_time_when_meeting_threshold_exactly(tmp_path, capsys):
    """AC3: a card with cycle time exactly 5 days and a thresholds file with
    cycle_time_days 5 produces no ⚠️ marker, because meeting the threshold
    exactly is not a breach."""
    card = {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"cycle_time_days": 5}))
    exit_code = main([str(cards_path), "--markdown", "--thresholds", str(thresholds_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- **Cycle time**: 5 days" in captured.out
    assert "⚠️" not in captured.out


def test_markdown_has_no_flags_without_thresholds_flag(tmp_path, capsys):
    """AC4: without --thresholds, the markdown output contains no ⚠️ markers and
    the metric lines are identical to the current behaviour."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "⚠️" not in captured.out
    assert "- **Cycle time**: 4 days" in captured.out
    assert "- **Lead time**: 6 days" in captured.out
    assert "- **Throughput**: 1 cards" in captured.out


def test_invalid_thresholds_file_exits_2(tmp_path, capsys):
    """AC5: a thresholds file that is not valid JSON exits with code 2, writes an
    error to stderr that includes sprint-metrics, and writes nothing to stdout."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text("not valid json")
    exit_code = main([str(cards_path), "--markdown", "--thresholds", str(thresholds_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "sprint-metrics" in captured.err
    assert captured.out == ""
