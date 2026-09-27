"""Tests that the README documents installation and basic usage."""

import re
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
