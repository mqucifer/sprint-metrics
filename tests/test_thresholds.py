"""Tests for threshold flagging in the markdown report."""


import pytest

from sprint_metrics.thresholds import _load_thresholds, calculate_flags


def test_calculate_flags_cycle_time_breached_lead_time_not():
    """AC1: a card with cycle time 7 days (exceeds default of 5) and lead time 7 days
    (equals default of 7, not exceeded) produces flags where cycle_time_days is True
    and lead_time_days is False."""
    cards = [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}]
    flags = calculate_flags(cards)
    assert flags["cycle_time_days"] is True
    assert flags["lead_time_days"] is False


def test_load_thresholds_raises_type_error_for_list():
    """AC2: a JSON list instead of an object raises TypeError mentioning thresholds."""
    with pytest.raises(TypeError, match="thresholds"):
        _load_thresholds('["cycle_time_days", 3]')


def test_calculate_flags_first_attempt_rate_below_threshold():
    """AC7: 5 cards where 2 have attempts 1 and 3 have attempts > 1, with default
    thresholds, produces flags where first_attempt_rate_percent is True (40 < 80)."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 2,
            "failure_class": "parse",
            "failure_role": "Developer",
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 3,
            "failure_class": "parse",
            "failure_role": "Developer",
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 2,
            "failure_class": "check",
            "failure_role": "Code Reviewer",
        },
    ]
    flags = calculate_flags(cards)
    assert flags["first_attempt_rate_percent"] is True


def test_calculate_flags_first_attempt_rate_above_threshold():
    """AC8: 5 cards all with attempts 1, with default threshold 80, produces flags
    where first_attempt_rate_percent is False (100 is not below 80)."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
    ] * 5
    flags = calculate_flags(cards)
    assert flags["first_attempt_rate_percent"] is False
