"""Tests for the --prior flag on the sprint-metrics command."""

import json

from sprint_metrics import main


def test_prior_flag_shows_prior_row_in_default_table(tmp_path, capsys):
    """AC1: a current card started 4 days before completion and a prior card started
    6 days before completion, run with --prior, exit 0 and show a Current row with
    cycle time 4 days, lead time 6 days, throughput 1, and a Prior row with cycle
    time 6 days, lead time 6 days, throughput 1."""
    current = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    prior = {"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([current]))
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps([prior]))
    exit_code = main([str(cards_path), "--prior", str(prior_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in captured.out
    assert "| Prior | 6 days | 6 days | 1 | 0 | 0 days | 0% |" in captured.out
    assert captured.out.index("| Current |") < captured.out.index("| Prior |")


def test_prior_flag_invalid_json_exits_2(tmp_path, capsys):
    """AC2: a prior file that is not valid JSON, run with --prior, exits 2, writes
    an error to stderr containing sprint-metrics, and writes nothing to stdout."""
    current = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([current]))
    prior_path = tmp_path / "bad.json"
    prior_path.write_text("not valid json")
    exit_code = main([str(cards_path), "--prior", str(prior_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "sprint-metrics" in captured.err
    assert captured.out == ""


def test_no_prior_flag_shows_only_current_row(tmp_path, capsys):
    """AC3: without --prior, the default table shows a Current row and no Prior row."""
    current = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([current]))
    exit_code = main([str(cards_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| Current |" in captured.out
    assert "| Prior |" not in captured.out
