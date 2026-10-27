"""Tests for the metric calculations in sprint_metrics.metrics."""

from datetime import UTC

from sprint_metrics.card import Card
from sprint_metrics.metrics import (
    _mean_days,
    _peak_occupancy,
    _state_windows,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_failure_breakdown,
    calculate_first_attempt_rate,
    calculate_throughput,
    calculate_top_failure_causes,
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


def test_calculate_first_attempt_rate_mixed():
    """AC1: 5 completed cards where 4 have attempts 1 and 1 has attempts 2 returns 80."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
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
    ]
    assert calculate_first_attempt_rate(cards) == 80


def test_calculate_first_attempt_rate_empty():
    """AC2: an empty list of cards returns 0."""
    assert calculate_first_attempt_rate([]) == 0


def test_calculate_failure_breakdown_grouped():
    """AC3: 3 cards with failure data return a breakdown sorted by count descending."""
    cards = [
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
    result = calculate_failure_breakdown(cards)
    assert result[0] == ("parse", "Developer", 2)
    assert result[1] == ("check", "Code Reviewer", 1)


def test_calculate_failure_breakdown_empty_when_all_first_attempt():
    """AC4: all cards have attempts 1, so the breakdown is an empty list."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07"},
    ]
    assert calculate_failure_breakdown(cards) == []


def test_failure_breakdown_counts_returns_not_stories():
    """AC1: a card whose failures list holds three returns (VERIFY/Review x2,
    SCHEMA/QA x1) produces one item per (class, role) return group, counting
    returns not stories."""
    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 3,
            "failures": [
                {"failure_class": "VERIFY", "failure_role": "Review"},
                {"failure_class": "VERIFY", "failure_role": "Review"},
                {"failure_class": "SCHEMA", "failure_role": "QA"},
            ],
        },
    ]
    result = calculate_failure_breakdown(cards)
    assert result == [("VERIFY", "Review", 2), ("SCHEMA", "QA", 1)]


def test_top_failure_causes_separate_entries_same_class_different_role():
    """AC4: two returns sharing class VERIFY but with different roles (Developer,
    Reviewer) yield two separate entries in top_failure_causes, each naming both
    class and role; a legacy card with only failure_class and no role keeps the
    class alone (empty role)."""
    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 2,
            "failures": [
                {"failure_class": "VERIFY", "failure_role": "Developer"},
                {"failure_class": "VERIFY", "failure_role": "Reviewer"},
            ],
        },
    ]
    result = calculate_top_failure_causes(cards)
    assert ("VERIFY", "Developer", 1) in result
    assert ("VERIFY", "Reviewer", 1) in result
    assert len(result) == 2
    # 'VERIFY' alone is not a key: each entry names both class and role
    for _cls, role, _count in result:
        assert role != ""


def test_top_failure_causes_tie_break_alphabetical():
    """AC5: returns whose (class, role) groups tie in count are ordered
    alphabetically in top_failure_causes (by class then role), while the full
    failure_breakdown preserves first-encounter order (stable sort)."""
    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 3,
            "failures": [
                {"failure_class": "ZULU", "failure_role": "QA"},
                {"failure_class": "ALPHA", "failure_role": "Review"},
            ],
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 3,
            "failures": [
                {"failure_class": "ALPHA", "failure_role": "Review"},
                {"failure_class": "ZULU", "failure_role": "QA"},
            ],
        },
    ]
    # Both groups have count 2. Top-3 ties broken alphabetically: ALPHA before ZULU.
    top = calculate_top_failure_causes(cards)
    assert top == [("ALPHA", "Review", 2), ("ZULU", "QA", 2)]

    # Full breakdown: count descending, ties in first-encounter order (stable).
    # ZULU was first encountered in card 1, so it comes first.
    breakdown = calculate_failure_breakdown(cards)
    assert breakdown == [("ZULU", "QA", 2), ("ALPHA", "Review", 2)]


def test_calculate_first_attempt_rate_half():
    """AC5: 4 cards where 2 have attempts 1 and 2 have attempts > 1 returns 50."""
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
            "failure_class": "check",
            "failure_role": "Code Reviewer",
        },
    ]
    assert calculate_first_attempt_rate(cards) == 50


def test_all_metrics_includes_new_metrics():
    """AC6: ALL_METRICS contains first_attempt_rate_percent and failure_breakdown."""
    from sprint_metrics.metrics import ALL_METRICS

    assert "first_attempt_rate_percent" in ALL_METRICS
    assert "failure_breakdown" in ALL_METRICS


def test_calculate_points_delivered_sums_completed_only():
    """AC1: two completed cards (points 5 and 3) plus one in-flight (points 2) gives 8."""
    from sprint_metrics.metrics import calculate_points_delivered

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "points": 5,
            "attempts": 1,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "points": 3,
            "attempts": 2,
        },
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "", "points": 2},
    ]
    assert calculate_points_delivered(cards) == 8


def test_calculate_points_delivered_none_points_contribute_zero():
    """AC2: a completed card with no points value contributes 0."""
    from sprint_metrics.metrics import calculate_points_delivered

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 1,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "points": 3,
            "attempts": 1,
        },
    ]
    assert calculate_points_delivered(cards) == 3


def test_calculate_first_attempt_counts():
    """AC3: three completed cards (two attempts=1, one attempts=2) gives (2, 3)."""
    from sprint_metrics.metrics import calculate_first_attempt_counts

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 1,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 1,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 2,
        },
    ]
    assert calculate_first_attempt_counts(cards) == (2, 3)


def test_calculate_points_and_first_attempt_empty():
    """AC4: empty list gives sum=0, numerator=0, denominator=0."""
    from sprint_metrics.metrics import calculate_first_attempt_counts, calculate_points_delivered

    assert calculate_points_delivered([]) == 0
    assert calculate_first_attempt_counts([]) == (0, 0)


def test_all_metrics_grew_by_four():
    """ALL_METRICS holds 31 entries, including the two sub-day minute metrics, the eight cost
    metrics, the rework sent-backs count, the two DORA measures, the working-time measure, the
    two cost-by-kind measures, and the two model-time split measures; the escalation measures
    are gone (#776)."""
    from sprint_metrics.metrics import ALL_METRICS

    assert len(ALL_METRICS) == 31
    assert "escalation_count" not in ALL_METRICS
    assert "escalation_rate_percent" not in ALL_METRICS
    new_metrics = {
        "points_delivered",
        "first_attempt_numerator",
        "first_attempt_denominator",
        "superseded_count",
        "superseded_points",
        "superseded_breakdown",
        "sent_backs_count",
        "release_frequency",
        "dora_lead_time_days",
    }
    minute_metrics = {
        "cycle_time_minutes",
        "lead_time_minutes",
        "working_time_minutes",
        "addition_working_time_minutes",
        "change_working_time_minutes",
        "model_time_split_refinement_minutes",
        "model_time_split_delivery_minutes",
    }
    cost_metrics = {
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
        "cached_input_percent",
        "reasoning_output_percent",
    }
    assert new_metrics.issubset(ALL_METRICS)
    assert minute_metrics.issubset(ALL_METRICS)
    assert cost_metrics.issubset(ALL_METRICS)
    existing = {
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "first_attempt_rate_percent",
        "failure_breakdown",
    }
    assert new_metrics.isdisjoint(existing)
    assert minute_metrics.isdisjoint(existing)
    assert cost_metrics.isdisjoint(existing)
    for name in new_metrics | minute_metrics | cost_metrics:
        assert name == name.lower() and "_" in name


def test_calculate_points_delivered_excludes_in_flight():
    """AC7: three completed (5+3+2) + one in-flight (10) gives 10."""
    from sprint_metrics.metrics import calculate_points_delivered

    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07", "points": 5},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07", "points": 3},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-07", "points": 2},
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "", "points": 10},
    ]
    assert calculate_points_delivered(cards) == 10


def test_calculate_first_attempt_counts_two_completed():
    """AC8: two completed (attempts 1 and 3), zero in-flight gives (1, 2)."""
    from sprint_metrics.metrics import calculate_first_attempt_counts

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 1,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-07",
            "attempts": 3,
        },
    ]
    assert calculate_first_attempt_counts(cards) == (1, 2)


def test_calculate_superseded_count():
    """AC1: two of three cards are superseded, so the count is 2."""
    from sprint_metrics.metrics import calculate_superseded_count

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-05",
            "superseded": True,
            "superseded_because": "sponsor",
            "points": 5,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-06",
            "superseded": True,
            "superseded_because": "story_problem",
            "points": 3,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-05",
            "points": 2,
        },
    ]
    assert calculate_superseded_count(cards) == 2


def test_calculate_superseded_points():
    """AC2: two superseded cards with points 5 and 3 give a total of 8."""
    from sprint_metrics.metrics import calculate_superseded_points

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-05",
            "superseded": True,
            "superseded_because": "sponsor",
            "points": 5,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-06",
            "superseded": True,
            "superseded_because": "story_problem",
            "points": 3,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-05",
            "points": 2,
        },
    ]
    assert calculate_superseded_points(cards) == 8


def test_calculate_superseded_breakdown():
    """AC3: one card superseded because 'sponsor' and one because 'story_problem'."""
    from sprint_metrics.metrics import calculate_superseded_breakdown

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-05",
            "superseded": True,
            "superseded_because": "sponsor",
            "points": 5,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-06",
            "superseded": True,
            "superseded_because": "story_problem",
            "points": 3,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "completed": "2024-01-05",
            "points": 2,
        },
    ]
    assert calculate_superseded_breakdown(cards) == {"sponsor": 1, "story_problem": 1}


def test_calculate_superseded_empty():
    """AC4: an empty list gives count 0, points 0, and both reasons at 0."""
    from sprint_metrics.metrics import (
        calculate_superseded_breakdown,
        calculate_superseded_count,
        calculate_superseded_points,
    )

    assert calculate_superseded_count([]) == 0
    assert calculate_superseded_points([]) == 0
    assert calculate_superseded_breakdown([]) == {"sponsor": 0, "story_problem": 0}


def test_wip_violations_excludes_superseded():
    """AC5: one in-flight card and one superseded card both started on the same day,
    with WIP limit 1 for In Progress, produces 0 violations because the superseded
    card is excluded from occupancy."""
    from sprint_metrics.metrics import calculate_wip_violations

    cards = [
        {"created": "2024-01-01", "started": "2024-01-05"},
        {
            "created": "2024-01-01",
            "started": "2024-01-05",
            "superseded": True,
            "superseded_because": "sponsor",
        },
    ]
    assert calculate_wip_violations(cards, {"In Progress": 1}) == 0


def test_blocked_aging_excludes_superseded():
    """AC6: a superseded card carrying a blocked_since date does not contribute
    to blocked aging."""
    from datetime import date

    from sprint_metrics.metrics import calculate_blocked_aging

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-02",
            "blocked_since": "2024-01-05",
            "superseded": True,
            "superseded_because": "sponsor",
        },
    ]
    assert calculate_blocked_aging(cards, as_of=date(2024, 1, 10)) == 0


def test_all_metrics_includes_superseded():
    """AC7: the three new metric names are members of ALL_METRICS."""
    from sprint_metrics.metrics import ALL_METRICS

    assert "superseded_count" in ALL_METRICS
    assert "superseded_points" in ALL_METRICS
    assert "superseded_breakdown" in ALL_METRICS


def test_cycle_and_lead_time_minutes_single_card():
    """AC1: one completed card with sub-day timestamps yields 686 min cycle and 3686 min lead."""
    from datetime import date, datetime

    from sprint_metrics.metrics import calculate_cycle_time_minutes, calculate_lead_time_minutes

    card = Card(
        created=date(2024, 1, 1),
        completed=date(2024, 1, 3),
        created_at=datetime(2024, 1, 1, 8, 0, tzinfo=UTC),
        started_at=datetime(2024, 1, 3, 10, 0, tzinfo=UTC),
        completed_at=datetime(2024, 1, 3, 21, 26, tzinfo=UTC),
    )
    assert calculate_cycle_time_minutes([card]) == 686
    assert calculate_lead_time_minutes([card]) == 3686


def test_cycle_and_lead_time_minutes_empty():
    """AC2: an empty list of cards yields None for both minute metrics."""
    from sprint_metrics.metrics import calculate_cycle_time_minutes, calculate_lead_time_minutes

    assert calculate_cycle_time_minutes([]) is None
    assert calculate_lead_time_minutes([]) is None


def test_cycle_time_minutes_excludes_date_level_cards():
    """AC3: a card with only date-level fields is excluded; the mean uses the datetime card alone."""
    from datetime import date, datetime

    from sprint_metrics.metrics import calculate_cycle_time_minutes

    card_a = Card(
        created=date(2024, 1, 1),
        started=date(2024, 1, 3),
        completed=date(2024, 1, 3),
        started_at=datetime(2024, 1, 3, 10, 0, tzinfo=UTC),
        completed_at=datetime(2024, 1, 3, 21, 26, tzinfo=UTC),
    )
    card_b = Card(created=date(2024, 1, 1), started=date(2024, 1, 2), completed=date(2024, 1, 4))
    assert calculate_cycle_time_minutes([card_a, card_b]) == 686


def test_cycle_time_minutes_none_when_started_at_missing():
    """AC4: a completed card whose started_at is None contributes nothing, so the result is None."""
    from datetime import date, datetime

    from sprint_metrics.metrics import calculate_cycle_time_minutes

    card = Card(
        created=date(2024, 1, 1),
        completed=date(2024, 1, 3),
        completed_at=datetime(2024, 1, 3, 21, 26, tzinfo=UTC),
    )
    assert calculate_cycle_time_minutes([card]) is None


def test_all_metrics_includes_minute_metrics():
    """AC5: ALL_METRICS contains cycle_time_minutes and lead_time_minutes."""
    from sprint_metrics.metrics import ALL_METRICS

    assert "cycle_time_minutes" in ALL_METRICS
    assert "lead_time_minutes" in ALL_METRICS


def test_cycle_and_lead_time_minutes_mean_two_completed():
    """AC6: the mean of two completed cards' sub-day spans is 420 min cycle and 974 min lead."""
    from datetime import date, datetime

    from sprint_metrics.metrics import calculate_cycle_time_minutes, calculate_lead_time_minutes

    card_a = Card(
        created=date(2026, 10, 11),
        completed=date(2026, 10, 11),
        created_at=datetime(2026, 10, 11, 4, 20, 12, tzinfo=UTC),
        started_at=datetime(2026, 10, 11, 7, 31, 56, tzinfo=UTC),
        completed_at=datetime(2026, 10, 11, 18, 57, 48, tzinfo=UTC),
    )
    card_b = Card(
        created=date(2026, 10, 11),
        completed=date(2026, 10, 11),
        created_at=datetime(2026, 10, 11, 4, 20, 17, tzinfo=UTC),
        started_at=datetime(2026, 10, 11, 19, 35, 24, tzinfo=UTC),
        completed_at=datetime(2026, 10, 11, 22, 9, 38, tzinfo=UTC),
    )
    assert calculate_cycle_time_minutes([card_a, card_b]) == 420
    assert calculate_lead_time_minutes([card_a, card_b]) == 974


def test_cycle_time_minutes_excludes_in_flight_card():
    """AC7: an in-flight card with sub-day timestamps does not contribute, so the result is None."""
    from datetime import date, datetime

    from sprint_metrics.metrics import calculate_cycle_time_minutes

    card = Card(
        created=date(2024, 1, 1),
        created_at=datetime(2024, 1, 1, 8, 0, tzinfo=UTC),
        started_at=datetime(2024, 1, 3, 10, 0, tzinfo=UTC),
        completed_at=datetime(2024, 1, 3, 21, 26, tzinfo=UTC),
    )
    assert card.is_completed is False
    assert calculate_cycle_time_minutes([card]) is None


def _cost_card(
    model_seconds=None,
    input_tokens=None,
    cached_input_tokens=None,
    output_tokens=None,
    reasoning_output_tokens=None,
    card_id=None,
):
    """A completed Card with optional cost fields set."""
    from datetime import date

    return Card(
        created=date(2024, 1, 1),
        started=date(2024, 1, 2),
        completed=date(2024, 1, 3),
        model_seconds=model_seconds,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        card_id=card_id,
    )


def test_cost_metrics_model_minutes_middle_and_total():
    """AC4: the model-minutes cost metrics report the median and sum of per-story whole minutes."""
    from sprint_metrics.metrics import (
        calculate_model_minutes_middle,
        calculate_model_minutes_total,
    )

    # model_seconds 3480, 5400, 120 -> whole minutes 58, 90, 2
    cards = [
        _cost_card(model_seconds=3480, input_tokens=1, output_tokens=1, card_id="a"),
        _cost_card(model_seconds=5400, input_tokens=1, output_tokens=1, card_id="b"),
        _cost_card(model_seconds=120, input_tokens=1, output_tokens=1, card_id="c"),
    ]
    assert calculate_model_minutes_middle(cards) == 58
    assert calculate_model_minutes_total(cards) == 150


def test_cost_metrics_tokens_middle_and_total():
    """AC4: the input/output token cost metrics report the median and sum across costed stories."""
    from sprint_metrics.metrics import (
        calculate_input_tokens_middle,
        calculate_input_tokens_total,
        calculate_output_tokens_middle,
        calculate_output_tokens_total,
    )

    cards = [
        _cost_card(model_seconds=60, input_tokens=2500, output_tokens=600, card_id="a"),
        _cost_card(model_seconds=60, input_tokens=4000, output_tokens=1200, card_id="b"),
        _cost_card(model_seconds=60, input_tokens=8000, output_tokens=3800, card_id="c"),
    ]
    assert calculate_input_tokens_middle(cards) == 4000
    assert calculate_input_tokens_total(cards) == 14500
    assert calculate_output_tokens_middle(cards) == 1200
    assert calculate_output_tokens_total(cards) == 5600


def test_cost_metrics_percents_are_sprint_combined():
    """AC4: the two cost percents are the sprint's combined shares, not a story's own share."""
    from sprint_metrics.metrics import (
        calculate_cached_input_percent,
        calculate_reasoning_output_percent,
    )

    # total input 10000, cached 4500 -> 45%; total output 5000, reasoning 1500 -> 30%
    cards = [
        _cost_card(
            model_seconds=60,
            input_tokens=5000,
            cached_input_tokens=2000,
            output_tokens=3000,
            reasoning_output_tokens=600,
            card_id="a",
        ),
        _cost_card(
            model_seconds=60,
            input_tokens=5000,
            cached_input_tokens=2500,
            output_tokens=2000,
            reasoning_output_tokens=900,
            card_id="b",
        ),
    ]
    assert calculate_cached_input_percent(cards) == 45
    assert calculate_reasoning_output_percent(cards) == 30


def test_cost_metrics_none_when_no_costed_story():
    """AC4: every cost metric is None when no story carries cost, including an event-bearing sprint."""
    from sprint_metrics.metrics import (
        calculate_cached_input_percent,
        calculate_input_tokens_middle,
        calculate_input_tokens_total,
        calculate_model_minutes_middle,
        calculate_model_minutes_total,
        calculate_output_tokens_middle,
        calculate_output_tokens_total,
        calculate_reasoning_output_percent,
    )

    bare = _cost_card()
    assert calculate_model_minutes_middle([bare]) is None
    assert calculate_model_minutes_total([bare]) is None
    assert calculate_input_tokens_middle([bare]) is None
    assert calculate_input_tokens_total([bare]) is None
    assert calculate_output_tokens_middle([bare]) is None
    assert calculate_output_tokens_total([bare]) is None
    assert calculate_cached_input_percent([bare]) is None
    assert calculate_reasoning_output_percent([bare]) is None
    assert calculate_model_minutes_middle([]) is None


def test_metric_value_dispatches_eight_cost_metrics():
    """AC4/AC8: metric_value accepts each cost name and returns that sprint's integer value."""
    from sprint_metrics.metrics import (
        calculate_cached_input_percent,
        calculate_input_tokens_middle,
        calculate_input_tokens_total,
        calculate_model_minutes_middle,
        calculate_model_minutes_total,
        calculate_output_tokens_middle,
        calculate_output_tokens_total,
        calculate_reasoning_output_percent,
        metric_value,
    )

    cards = [
        _cost_card(
            model_seconds=3480,
            input_tokens=4000,
            cached_input_tokens=1800,
            output_tokens=900,
            reasoning_output_tokens=200,
            card_id="a",
        ),
        _cost_card(
            model_seconds=5400,
            input_tokens=12000,
            cached_input_tokens=5840,
            output_tokens=4800,
            reasoning_output_tokens=1200,
            card_id="b",
        ),
    ]
    expected = {
        "model_minutes_middle": calculate_model_minutes_middle(cards),
        "model_minutes_total": calculate_model_minutes_total(cards),
        "input_tokens_middle": calculate_input_tokens_middle(cards),
        "input_tokens_total": calculate_input_tokens_total(cards),
        "output_tokens_middle": calculate_output_tokens_middle(cards),
        "output_tokens_total": calculate_output_tokens_total(cards),
        "cached_input_percent": calculate_cached_input_percent(cards),
        "reasoning_output_percent": calculate_reasoning_output_percent(cards),
    }
    for name, value in expected.items():
        assert metric_value(name, cards) == value
        assert isinstance(value, int)
