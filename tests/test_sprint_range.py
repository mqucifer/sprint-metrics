"""Tests for the --sprint-range flag on the sprint-metrics command."""


import pytest

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}


def test_parse_sprint_range_returns_label_list():
    """AC1: _parse_sprint_range called on '2024-01..2024-03' from
    sprint_metrics.sprint_range returns ['2024-01', '2024-02', '2024-03']."""
    from sprint_metrics.sprint_range import _parse_sprint_range

    assert _parse_sprint_range("2024-01..2024-03") == ["2024-01", "2024-02", "2024-03"]


def test_parse_sprint_range_invalid_month_raises_value_error():
    """AC2: _parse_sprint_range called on '2024-13..2024-01' from
    sprint_metrics.sprint_range raises ValueError whose message contains '2024-13'."""
    from sprint_metrics.sprint_range import _parse_sprint_range

    with pytest.raises(ValueError, match="2024-13"):
        _parse_sprint_range("2024-13..2024-01")


def test_load_sprints_list_raises_type_error():
    """AC3: _load_sprints called on a JSON list from sprint_metrics.sprint_range
    raises TypeError whose message contains 'JSON object'."""
    from sprint_metrics.sprint_range import _load_sprints

    with pytest.raises(TypeError, match="JSON object"):
        _load_sprints('[{"created": "2024-01-01"}]')


def test_format_sprint_range_table_order_and_no_current():
    """AC4: format_sprint_range_table with two sprints shows a row for 2024-01
    before a row for 2024-02, and neither row is labelled 'Current'."""
    from datetime import date

    from sprint_metrics.card import Card
    from sprint_metrics.sprint_range import format_sprint_range_table

    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3), completed=date(2024, 1, 7))
    sprints = {"2024-01": [card], "2024-02": [card]}
    labels = ["2024-01", "2024-02"]
    result = format_sprint_range_table(sprints, labels)

    idx_01 = result.index("| 2024-01 |")
    idx_02 = result.index("| 2024-02 |")
    assert idx_01 < idx_02
    assert "| Current |" not in result
