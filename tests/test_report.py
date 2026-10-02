"""Tests for the single-sprint formatters in sprint_metrics.report."""

from sprint_metrics.report import format_markdown_report, format_performance_table


def test_format_performance_table_completed_card():
    """AC1: one completed card (created 2024-01-01, started 2024-01-03, completed
    2024-01-07) with no WIP limits, no escalations, and no prior cards produces
    a table containing the Current row with 4 days cycle time and 6 days lead time."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    result = format_performance_table([card])
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in result


def test_format_markdown_report_empty_cards():
    """AC2: an empty list of cards produces a markdown report containing
    'No performance data available' and not containing '## Current Sprint'."""
    result = format_markdown_report([])
    assert "No performance data available" in result
    assert "## Current Sprint" not in result


def test_format_performance_table_thresholds_flag_cycle_time_only():
    """AC3: one completed card with cycle time 4 days and thresholds
    {"cycle_time_days": 3} produces a table where the cycle time cell has a
    warning marker but the lead time cell does not."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    result = format_performance_table([card], thresholds={"cycle_time_days": 3})
    assert "| Current | 4 days \u26a0\ufe0f | 6 days | 1 | 0 | 0 days | 0% |" in result


def test_card_detail_shows_attempts_and_failure_class():
    """AC2: a completed card with attempts=2 and failure_class='parse' shows both values in its Card Detail row."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "parse",
    }
    result = format_markdown_report([card])
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    data_lines = [
        line
        for line in lines[detail_idx + 4 :]
        if line.startswith("|") and not line.startswith("|-")
    ]
    assert len(data_lines) == 1
    assert "2" in data_lines[0]
    assert "parse" in data_lines[0]


def test_card_detail_shows_blocked_since_date():
    """AC4: a blocked card's blocked_since date appears in its Card Detail row."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-02",
        "blocked_since": "2024-01-05",
    }
    result = format_markdown_report([card])
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    section_body = "\n".join(lines[detail_idx:])
    assert "2024-01-05" in section_body


def test_card_detail_one_line_per_card_with_correct_dates():
    """AC6: exactly one data line per card, with blocked_since on the same line as its created date."""
    cards = [
        {"created": "2024-07-01", "started": "2024-07-02", "completed": "2024-07-05"},
        {"created": "2024-07-03", "started": "2024-07-05"},
        {"created": "2024-07-03", "started": "2024-07-04", "blocked_since": "2024-07-07"},
    ]
    result = format_markdown_report(cards)
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    data_lines = [
        line
        for line in lines[detail_idx + 4 :]
        if line.startswith("|") and not line.startswith("|-")
    ]
    assert len(data_lines) == 3
    for line in data_lines:
        assert "2024-07-01" in line or "2024-07-03" in line
    blocked_lines = [line for line in data_lines if "2024-07-07" in line]
    assert len(blocked_lines) == 1
    assert "2024-07-03" in blocked_lines[0]


def test_card_detail_shows_attempts_failure_class_and_role():
    """AC7: a completed card shows its attempts, failure_class, and failure_role in its Card Detail row."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 3,
        "failure_class": "timeout",
        "failure_role": "infra",
    }
    result = format_markdown_report([card])
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    data_lines = [
        line
        for line in lines[detail_idx + 4 :]
        if line.startswith("|") and not line.startswith("|-")
    ]
    assert len(data_lines) == 1
    assert "3" in data_lines[0]
    assert "timeout" in data_lines[0]
    assert "infra" in data_lines[0]


def test_card_detail_section_after_definitions_shows_both_cards():
    """AC1: Card Detail appears after Definitions and lists both cards by created date."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "started": "2024-01-04"},
    ]
    result = format_markdown_report(cards)
    lines = result.splitlines()
    assert lines.index("## Card Detail") > lines.index("## Definitions")
    section_body = "\n".join(lines[lines.index("## Card Detail") :])
    assert "2024-01-01" in section_body
    assert "2024-01-02" in section_body


def test_card_detail_omitted_when_no_cards():
    """AC3: with no cards, the report has Definitions but no Card Detail section."""
    result = format_markdown_report([])
    assert "## Definitions" in result
    assert "## Card Detail" not in result
