"""Tests for the built-in threshold flags the service reports."""

from sprint_metrics.thresholds import DEFAULT_THRESHOLDS, calculate_flags


def test_calculate_flags_cycle_time_breached_lead_time_not():
    """AC1: a card with cycle time 7 days (exceeds default of 5) and lead time 7 days
    (equals default of 7, not exceeded) produces flags where cycle_time_days is True
    and lead_time_days is False."""
    cards = [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}]
    flags = calculate_flags(cards)
    assert flags["cycle_time_days"] is True
    assert flags["lead_time_days"] is False


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


KEPT_MEASURES = [
        "cycle_time_days",
        "lead_time_days",
        "cycle_time_minutes",
        "lead_time_minutes",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "first_attempt_rate_percent",
    ]


def test_flags_judge_exactly_the_eight_kept_measures():
    """#775 AC1: the defaults and the flags cover exactly the eight kept measures;
    the escalation rate is no longer judged."""
    cards = [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}]
    assert sorted(DEFAULT_THRESHOLDS) == sorted(KEPT_MEASURES)
    assert sorted(calculate_flags(cards)) == sorted(KEPT_MEASURES)


def test_override_naming_escalation_rate_produces_no_flag():
    """#775 AC2: a thresholds override naming escalation_rate_percent adds no
    escalation key to the flags, whatever its value."""
    cards = [{"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}]
    for value in (0, 10, 1000):
        flags = calculate_flags(cards, thresholds={"escalation_rate_percent": value})
        assert "escalation_rate_percent" not in flags
        assert sorted(flags) == sorted(KEPT_MEASURES)
