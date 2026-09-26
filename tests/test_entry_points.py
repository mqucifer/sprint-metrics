"""Tests that both entry points resolve main from sprint_metrics.cli."""


def test_console_script_produces_expected_output(tmp_path, capsys):
    """AC1: the sprint-metrics console script resolves main from sprint_metrics.cli
    and, given a completed card, exits 0 and prints the expected table row."""
    import json
    import subprocess
    import sys

    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))

    result = subprocess.run(
        [sys.executable, "-m", "sprint_metrics", str(cards_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in result.stdout


def test_python_minus_m_produces_expected_output(tmp_path, capsys):
    """AC2: python -m sprint_metrics resolves main from sprint_metrics.cli and,
    given a completed card, exits 0 and prints the expected table row."""
    import json
    import subprocess
    import sys

    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))

    result = subprocess.run(
        [sys.executable, "-m", "sprint_metrics", str(cards_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in result.stdout


def test_import_main_from_package_produces_expected_output(tmp_path, capsys):
    """AC3: importing main from sprint_metrics and invoking it with a completed card
    exits 0 and prints the expected table row, identical to the other entry points."""
    import json

    from sprint_metrics import main

    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))

    exit_code = main([str(cards_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in captured.out
