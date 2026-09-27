"""Tests that the README documents installation and basic usage."""

import json
import re
from datetime import date
from pathlib import Path

README = Path(__file__).parent.parent / "README.md"


def _readme() -> str:
    return README.read_text()


def _section(text: str, heading: str) -> str:
    """Return the body of a level-2 section, up to the next level-2 heading or EOF."""
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"README.md has no section '## {heading}'"
    return match.group(1)


def test_readme_installation_shows_uv_pip_install_with_version_tag():
    """AC1: the installation section contains a uv pip install command with the git URL
    followed by a version tag, and states the sprint-metrics command is on PATH."""
    section = _section(_readme(), "Installation")
    assert "uv pip install" in section
    assert "git+https://github.com/mqucifer/sprint-metrics.git@" in section
    match = re.search(r"sprint-metrics\.git@v\d+\.\d+\.\d+", section)
    assert match is not None, "expected a version tag like v0.1.0 after the git URL"
    assert "PATH" in section


def test_readme_installation_states_python_312_and_no_third_party_packages():
    """AC2: the installation section states Python 3.12 is required and that no
    third-party runtime packages are needed."""
    section = _section(_readme(), "Installation")
    assert "3.12" in section
    assert "no third-party" in section.lower()


def test_readme_basic_usage_shows_minimal_invocation_and_stdin():
    """AC3: the basic-usage section shows sprint-metrics cards.json and states that
    omitting the file argument makes the tool read JSON from standard input."""
    section = _section(_readme(), "Basic usage")
    assert "sprint-metrics cards.json" in section
    assert "standard input" in section.lower()


def test_readme_input_format_shows_json_array_with_complete_and_partial_cards():
    """AC1: the input-format section shows a JSON array of card objects with at least one
    complete example card that includes created (ISO-8601), started, completed, and
    blocked_since, and at least one card showing an omitted optional key."""
    section = _section(_readme(), "Input format (cards.json)")
    assert '"created"' in section
    assert '"started"' in section
    assert '"completed"' in section
    assert '"blocked_since"' in section
    # At least two cards: one complete, one with omitted optional keys
    assert section.count('"created"') >= 2


def test_readme_input_format_states_created_only_required_and_top_level_array():
    """AC2: the input-format section states that created is the only required field per
    card and that the top-level JSON value must be an array (list), not an object."""
    section = _section(_readme(), "Input format (cards.json)")
    assert "only required" in section
    assert "array" in section
    assert "not an object" in section


def test_readme_input_format_states_empty_array_is_valid():
    """AC3: the input-format section states that an empty JSON array ([]) is valid input
    and produces a report in which every metric is zero."""
    section = _section(_readme(), "Input format (cards.json)")
    assert "[]" in section
    assert "zero" in section


def test_readme_worked_example_shows_input_command_and_output():
    """AC1: the worked-example section shows a complete cards.json (a JSON array
    containing at least two cards: at least one with a completed field set and
    at least one without), the exact sprint-metrics command to run, and the full
    resulting default-table output including the header row and the data row."""
    section = _section(_readme(), "Worked example")
    # A JSON array with at least two cards
    assert section.count('"created"') >= 2
    # At least one card has a completed field
    assert '"completed"' in section
    # The exact command
    assert "sprint-metrics cards.json" in section
    # The full table output: header row and data row
    assert "| Sprint |" in section
    assert "| Current |" in section


def test_readme_worked_example_throughput_and_cycle_time_are_correct():
    """AC2: the throughput value in the example table equals the count of cards in
    the shown input that have a completed field set to a date, and the cycle time
    value equals the average (rounded to nearest whole day) of the difference in
    days between each completed card's completed date and its started date."""
    section = _section(_readme(), "Worked example")
    json_match = re.search(r"```json\n(.*?)```", section, re.DOTALL)
    assert json_match is not None, "no JSON code block in worked example"
    cards = json.loads(json_match.group(1))
    completed_cards = [c for c in cards if c.get("completed")]
    expected_throughput = len(completed_cards)
    # Extract the data row from the table
    data_rows = [line for line in section.splitlines() if line.startswith("| Current |")]
    assert data_rows, "no data row in worked example table"
    cells = [c.strip() for c in data_rows[0].split("|") if c.strip()]
    # cells[0]=Sprint value, cells[1]=Cycle time, cells[2]=Lead time, cells[3]=Throughput
    assert cells[3] == str(expected_throughput), (
        f"throughput cell {cells[3]!r} != expected {expected_throughput}"
    )
    # Cycle time is the rounded average of (completed - started) days
    cycle_times = [
        (date.fromisoformat(c["completed"]) - date.fromisoformat(c["started"])).days
        for c in completed_cards
    ]
    expected_cycle = round(sum(cycle_times) / len(cycle_times))
    assert cells[1] == f"{expected_cycle} days", (
        f"cycle time cell {cells[1]!r} != expected {expected_cycle} days"
    )


def test_readme_worked_example_incomplete_card_excluded_from_metrics():
    """AC3: at least one card in the example input lacks a completed field, and the
    example demonstrates that this card does not appear in the throughput count or
    the cycle-time average."""
    section = _section(_readme(), "Worked example")
    json_match = re.search(r"```json\n(.*?)```", section, re.DOTALL)
    assert json_match is not None
    cards = json.loads(json_match.group(1))
    # At least one card lacks a completed field
    incomplete = [c for c in cards if not c.get("completed")]
    assert incomplete, "no card without completed field in example input"
    # Throughput equals the count of completed cards only (not total cards)
    completed_count = sum(1 for c in cards if c.get("completed"))
    total_count = len(cards)
    assert completed_count < total_count
    data_rows = [line for line in section.splitlines() if line.startswith("| Current |")]
    assert data_rows
    cells = [c.strip() for c in data_rows[0].split("|") if c.strip()]
    assert cells[3] == str(completed_count), (
        f"throughput {cells[3]!r} should be {completed_count} (completed only), "
        f"not {total_count} (all cards)"
    )
