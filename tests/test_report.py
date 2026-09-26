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
