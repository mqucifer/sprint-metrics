"""Tests for the metric calculations in sprint_metrics.metrics."""

import pytest

from sprint_metrics.card import Card
from sprint_metrics.metrics import (
    _load_wip_limits,
    _mean_days,
    _peak_occupancy,
    _state_windows,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)


def test_calculate_cycle_time_and_lead_time_returns_tuple():
    """AC1: one completed card with cycle time 4 and lead time 6 returns (4, 6)."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    assert calculate_cycle_time_and_lead_time(cards) == (4, 6)


def test_calculate_wip_violations_returns_one():
    """AC2: four in-flight cards with WIP limit 3 for In Progress returns 1 violation."""
    cards = [{"created": "2024-01-01", "started": "2024-01-02", "completed": ""}] * 4
    assert calculate_wip_violations(cards, {"In Progress": 3}) == 1


def test_load_wip_limits_raises_type_error_for_list():
    """AC3: a JSON list instead of an object raises TypeError mentioning WIP limits."""
    with pytest.raises(TypeError, match="WIP limits"):
        _load_wip_limits('["In Progress", 3]')


def test_calculate_throughput_counts_completed_cards():
    """Throughput is the count of completed cards."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": ""},
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
    ]
    assert calculate_throughput(cards) == 2


def test_calculate_throughput_is_zero_when_nothing_is_completed():
    """A sprint with only in-flight cards has zero throughput."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": ""},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": ""},
    ]
    assert calculate_throughput(cards) == 0


def test_calculate_throughput_is_zero_for_an_empty_sprint():
    """An empty sprint has zero throughput."""
    assert calculate_throughput([]) == 0


def test_calculate_blocked_aging_for_a_blocked_card():
    """A card blocked since 2024-01-02 and measured as of 2024-01-31 shows 29 days."""
    from datetime import date

    cards = [{"created": "2024-01-01", "blocked_since": "2024-01-02"}]
    assert calculate_blocked_aging(cards, as_of=date(2024, 1, 31)) == 29


def test_calculate_blocked_aging_is_zero_when_no_cards_blocked():
    """No cards are blocked, so blocked aging is 0."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    assert calculate_blocked_aging(cards) == 0


def test_calculate_escalation_rate_with_escalations():
    """With 2 escalations and 10 completed cards, the rate is 20%."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}] * 10
    assert calculate_escalation_rate(cards, escalations=2) == 20


def test_calculate_escalation_rate_is_zero_when_no_cards_completed():
    """With no completed cards the escalation rate is 0 regardless of escalations."""
    cards = [{"created": "2024-01-01", "started": "2024-01-02", "completed": ""}]
    assert calculate_escalation_rate(cards, escalations=5) == 0


def test_mean_days_returns_zero_for_empty_list():
    """_mean_days returns 0 for an empty list."""
    assert _mean_days([]) == 0


def test_mean_days_returns_rounded_average():
    """_mean_days returns the rounded average of the values."""
    assert _mean_days([4, 6]) == 5
    assert _mean_days([1, 2, 3]) == 2


def test_state_windows_for_completed_card():
    """_state_windows returns the correct windows for a fully completed card."""
    from datetime import date

    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3), completed=date(2024, 1, 7))
    windows = _state_windows(card)
    assert windows["To Do"] == (date(2024, 1, 1), date(2024, 1, 3))
    assert windows["In Progress"] == (date(2024, 1, 3), date(2024, 1, 7))
    assert windows["Completed"] == (date(2024, 1, 7), None)


def test_state_windows_for_in_flight_card():
    """_state_windows returns the correct windows for an in-flight card."""
    from datetime import date

    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3))
    windows = _state_windows(card)
    assert windows["To Do"] == (date(2024, 1, 1), date(2024, 1, 3))
    assert windows["In Progress"] == (date(2024, 1, 3), None)
    assert "Completed" not in windows


def test_peak_occupancy_counts_overlapping_cards():
    """_peak_occupancy returns the maximum number of cards in a state at once."""
    from datetime import date

    cards = [
        Card(created=date(2024, 1, 1), started=date(2024, 1, 2), completed=None),
        Card(created=date(2024, 1, 1), started=date(2024, 1, 2), completed=None),
        Card(created=date(2024, 1, 1), started=date(2024, 1, 2), completed=None),
        Card(created=date(2024, 1, 1), started=date(2024, 1, 2), completed=None),
    ]
    assert _peak_occupancy(cards, "In Progress") == 4


def test_peak_occupancy_is_zero_for_empty_cards():
    """_peak_occupancy returns 0 for an empty list of cards."""
    assert _peak_occupancy([], "In Progress") == 0
