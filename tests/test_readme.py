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


def _metrics_section() -> str:
    """Find the metrics section: a ## heading whose text contains 'metric' (case-insensitive)."""
    text = _readme()
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("## ") and "metric" in line.lower():
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("## "):
                    end = j
                    break
            return "\n".join(lines[i + 1 : end])
    raise AssertionError("README.md has no ## heading containing 'metric' (case-insensitive)")


def test_metrics_heading_contains_all_six_names():
    """AC1: a ## heading containing 'metric' exists, and beneath it all six metric names appear."""
    section = _metrics_section()
    section_lower = section.lower()
    for name in (
        "cycle time",
        "lead time",
        "throughput",
        "wip violations",
        "blocked aging",
        "escalation rate",
    ):
        assert name in section_lower, f"missing metric name {name!r} in the metrics section"


def test_cycle_time_computation_and_names():
    """AC2: the cycle time entry states its computation and lists all four output names."""
    section_raw = _metrics_section()
    section = section_raw.lower()
    for phrase in (
        "mean",
        "average",
        "completion date",
        "start date",
        "whole days",
        "rounded",
        "nearest whole day",
        "calculated only over cards that have a completion date",
    ):
        assert phrase in section, f"cycle time entry missing: {phrase!r}"
    assert "Cycle time" in section_raw
    assert "cycle_time_days" in section_raw
    assert "sprint_cycle_time_days" in section_raw


def test_wip_violations_computation_and_names():
    """AC3: the WIP violations entry states its computation and lists all four output names."""
    section_raw = _metrics_section()
    section = section_raw.lower()
    for phrase in (
        "count of board states",
        "maximum number of cards",
        "simultaneously",
        "exceeded",
        "configured limit",
        "only states with a configured limit can be in violation",
    ):
        assert phrase in section, f"WIP violations entry missing: {phrase!r}"
    assert "WIP violations" in section_raw
    assert "wip_violations" in section_raw
    assert "sprint_wip_violations" in section_raw


def test_throughput_lead_time_blocked_aging_escalation_computations():
    """AC4: throughput, lead time, blocked aging, and escalation rate each state their
    computation and list their table column, JSON key, markdown label, and Prometheus name."""
    section_raw = _metrics_section()
    section = section_raw.lower()

    # Throughput
    assert "count of cards with a completion date" in section
    assert "Throughput" in section_raw
    assert "throughput" in section_raw
    assert "sprint_throughput_cards" in section_raw

    # Lead time
    assert "completion date minus creation date" in section
    assert "Lead time" in section_raw
    assert "lead_time_days" in section_raw
    assert "sprint_lead_time_days" in section_raw

    # Blocked aging
    assert "maximum days any single card has been blocked" in section
    assert "Blocked aging" in section_raw
    assert "blocked_aging_days" in section_raw
    assert "sprint_blocked_aging_days" in section_raw

    # Escalation rate
    assert "number of escalations divided by the number of completed cards" in section
    assert "whole-number percentage" in section
    assert "Escalation rate" in section_raw
    assert "escalation_rate_percent" in section_raw
    assert "sprint_escalation_rate_percent" in section_raw


def test_completed_card_exclusion_rule():
    """AC5: states that a card is completed when it has a completion date, and that
    in-flight cards are excluded from cycle time, lead time, and throughput."""
    section = _metrics_section().lower()
    assert "completed when it has a completion date" in section
    assert "in-flight" in section
    assert "excluded from cycle time, lead time, and throughput" in section
