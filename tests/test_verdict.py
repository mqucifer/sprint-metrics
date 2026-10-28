"""Tests for the measure registry and the window verdict in sprint_metrics.verdict."""

import pytest

from sprint_metrics.verdict import MEASURE_REGISTRY, verdict, window_standouts


def test_lower_is_better_cycle_time_verdict():
    """AC1: cycle_time_days is registered lower-is-better; a first value of 5
    against a last of 3 reads "better", 3 against 5 reads "worse", and equal
    values read "flat"."""
    assert verdict("cycle_time_days", 5, 3) == "better"
    assert verdict("cycle_time_days", 3, 5) == "worse"
    assert verdict("cycle_time_days", 5, 5) == "flat"


def test_no_better_direction_carries_movement_not_quality():
    """AC2: first_attempt_numerator is registered with no better direction;
    first 2 against last 5 reads the movement "up", 5 against 2 reads "down",
    and equal values read "flat" — a measure with no better direction never
    carries "better" or "worse"."""
    assert verdict("first_attempt_numerator", 2, 5) == "up"
    assert verdict("first_attempt_numerator", 5, 2) == "down"
    assert verdict("first_attempt_numerator", 5, 5) == "flat"


def test_registered_extra_measure_is_judged_by_the_unmodified_verdict():
    """AC3: a measure the shipped registry does not carry, registered as
    higher-is-better in a registry the verdict function takes, reads
    "better", "worse", and "flat" from the registered direction — the verdict
    is driven purely by (measure, better-direction) pairs, so a new measure
    needs only a registry entry."""
    registry = {**MEASURE_REGISTRY, "sample_measure": ("higher", "count", "whole")}
    assert verdict("sample_measure", 2, 5, registry) == "better"
    assert verdict("sample_measure", 5, 2, registry) == "worse"
    assert verdict("sample_measure", 5, 5, registry) == "flat"


def test_shipped_registry_covers_every_scalar_range_measure():
    """AC4: the shipped registry covers exactly the scalar measures the /range
    sprint entry carries, with lower-is-better on the cycle and lead times,
    wip_violations, blocked_aging_days, superseded_count and superseded_points;
    higher-is-better on throughput, points_delivered and
    first_attempt_rate_percent; and no better direction on the first-attempt
    numerator and denominator and the six cost measures."""
    directions = {
        "cycle_time_days": "lower",
        "lead_time_days": "lower",
        "cycle_time_minutes": "lower",
        "lead_time_minutes": "lower",
        "throughput": "higher",
        "points_delivered": "higher",
        "wip_violations": "lower",
        "blocked_aging_days": "lower",
        "first_attempt_rate_percent": "higher",
        "first_attempt_numerator": None,
        "first_attempt_denominator": None,
        "superseded_count": "lower",
        "superseded_points": "lower",
        "model_minutes_middle": None,
        "model_minutes_total": None,
        "input_tokens_middle": None,
        "input_tokens_total": None,
        "output_tokens_middle": None,
        "output_tokens_total": None,
    }
    assert set(MEASURE_REGISTRY) == set(directions)
    for measure, direction in directions.items():
        assert MEASURE_REGISTRY[measure][0] == direction


def test_shipped_registry_carries_no_entry_for_the_non_scalar_items():
    """AC4: the breakdowns and the per-story list are not scalar measures, so
    the registry carries no entry for them."""
    for non_scalar in ("failure_breakdown", "top_failure_causes", "superseded_breakdown", "story_costs"):
        assert non_scalar not in MEASURE_REGISTRY


def test_shipped_registry_units_and_precisions_match_the_range_expressions():
    """AC5: the days measures carry "days", the minutes measures — including
    the model-cost minutes, whose display unit is whole model minutes — carry
    "minutes", the percent measures "percent", points_delivered and
    superseded_points "points", and the counts "count"; every entry's
    precision is "whole", matching the integer per-sprint values."""
    units = {
        "cycle_time_days": "days",
        "lead_time_days": "days",
        "blocked_aging_days": "days",
        "cycle_time_minutes": "minutes",
        "lead_time_minutes": "minutes",
        "model_minutes_middle": "minutes",
        "model_minutes_total": "minutes",
        "first_attempt_rate_percent": "percent",
        "points_delivered": "points",
        "superseded_points": "points",
        "throughput": "count",
        "wip_violations": "count",
        "first_attempt_numerator": "count",
        "first_attempt_denominator": "count",
        "superseded_count": "count",
        "input_tokens_middle": "count",
        "input_tokens_total": "count",
        "output_tokens_middle": "count",
        "output_tokens_total": "count",
    }
    for measure, unit in units.items():
        assert MEASURE_REGISTRY[measure][1] == unit
    for entry in MEASURE_REGISTRY.values():
        assert entry[2] == "whole"


def test_verdict_without_a_registry_entry_refuses_to_judge():
    """A measure the registry does not carry has no better direction to judge
    against; the verdict raises rather than invent one."""
    with pytest.raises(ValueError, match="unknown measure"):
        verdict("sample_measure", 1, 2)


def test_biggest_improvement_and_worst_dip_name_measure_sprints_size_and_unit():
    """AC1: with throughput 4, 5, 3, 8 and cycle_time_days 9, 8, 8, 7 across
    four data-bearing sprints, the biggest_improvement names throughput,
    2024-03 and 2024-04, size 5, unit count; the worst_dip names throughput,
    2024-02 and 2024-03, size 2, unit count."""
    sprints = {
        "2024-01": {"throughput": 4, "cycle_time_days": 9},
        "2024-02": {"throughput": 5, "cycle_time_days": 8},
        "2024-03": {"throughput": 3, "cycle_time_days": 8},
        "2024-04": {"throughput": 8, "cycle_time_days": 7},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03", "2024-04"]
    result = window_standouts(sprints, data_bearing)
    assert result["biggest_improvement"] == {
        "measure": "throughput",
        "from_sprint": "2024-03",
        "to_sprint": "2024-04",
        "size": 5,
        "unit": "count",
        "precision": "whole",
    }
    assert result["worst_dip"] == {
        "measure": "throughput",
        "from_sprint": "2024-02",
        "to_sprint": "2024-03",
        "size": 2,
        "unit": "count",
        "precision": "whole",
    }


def test_no_data_sprint_is_bridged_as_one_step():
    """AC1: a no-data sprint between two data-bearing sprints is bridged, so
    2024-01 to 2024-03 counts as one step when 2024-02 has no data."""
    sprints = {
        "2024-01": {"throughput": 2},
        "2024-02": {},
        "2024-03": {"throughput": 10},
    }
    data_bearing = ["2024-01", "2024-03"]
    result = window_standouts(sprints, data_bearing)
    assert result["biggest_improvement"] == {
        "measure": "throughput",
        "from_sprint": "2024-01",
        "to_sprint": "2024-03",
        "size": 8,
        "unit": "count",
        "precision": "whole",
    }


def test_turns_name_sprints_where_a_measure_changed_direction():
    """AC2: with throughput 4, 5, 3, 8, the turns list names exactly
    (sprint 2024-02, measure throughput) and (sprint 2024-03, measure
    throughput); cycle_time_days' flat step names no turn."""
    sprints = {
        "2024-01": {"throughput": 4, "cycle_time_days": 9},
        "2024-02": {"throughput": 5, "cycle_time_days": 8},
        "2024-03": {"throughput": 3, "cycle_time_days": 8},
        "2024-04": {"throughput": 8, "cycle_time_days": 7},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03", "2024-04"]
    result = window_standouts(sprints, data_bearing)
    assert result["turns"] == [
        {"sprint": "2024-02", "measure": "throughput"},
        {"sprint": "2024-03", "measure": "throughput"},
    ]


def test_no_turns_when_no_measure_changes_direction():
    """AC2: a window in which no measure changes direction carries an empty
    turns list."""
    sprints = {
        "2024-01": {"throughput": 3, "cycle_time_days": 10},
        "2024-02": {"throughput": 5, "cycle_time_days": 8},
        "2024-03": {"throughput": 7, "cycle_time_days": 6},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03"]
    result = window_standouts(sprints, data_bearing)
    assert result["turns"] == []


def test_two_data_bearing_sprints_flags_too_short():
    """AC3: a window with exactly two data-bearing sprints carries too_short
    true, while verdict entries are still present."""
    sprints = {
        "2024-01": {"throughput": 4},
        "2024-02": {"throughput": 6},
    }
    data_bearing = ["2024-01", "2024-02"]
    result = window_standouts(sprints, data_bearing)
    assert result["too_short"] is True
    # With two data-bearing sprints there is one step, so standouts can exist.
    assert result["biggest_improvement"] is not None
    assert result["turns"] == []


def test_three_data_bearing_sprints_not_too_short():
    """AC3: a window with three or more data-bearing sprints carries too_short
    false."""
    sprints = {
        "2024-01": {"throughput": 4},
        "2024-02": {"throughput": 5},
        "2024-03": {"throughput": 6},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03"]
    result = window_standouts(sprints, data_bearing)
    assert result["too_short"] is False


def test_zero_or_one_data_bearing_sprint_returns_null_standouts():
    """AC4: a window with zero or one data-bearing sprint has biggest_improvement
    and worst_dip null, turns empty, and too_short true."""
    # Zero data-bearing sprints
    sprints = {"2024-01": {}}
    result = window_standouts(sprints, [])
    assert result["biggest_improvement"] is None
    assert result["worst_dip"] is None
    assert result["turns"] == []
    assert result["too_short"] is True

    # One data-bearing sprint
    sprints2 = {"2024-01": {"throughput": 4}}
    result2 = window_standouts(sprints2, ["2024-01"])
    assert result2["biggest_improvement"] is None
    assert result2["worst_dip"] is None
    assert result2["turns"] == []
    assert result2["too_short"] is True


def test_tie_broken_by_earlier_sprint_pair_then_registry_order():
    """AC5: two improvements of equal magnitude in different sprint pairs — the
    earlier sprint pair wins; within the same pair the measure earlier in the
    registry order wins."""
    # Two pairs with the same improvement size: throughput improves by 3 in
    # both pairs (2024-01 to 2024-02 and 2024-02 to 2024-03). The earlier
    # pair (2024-01 to 2024-02) wins.
    sprints = {
        "2024-01": {"throughput": 4, "cycle_time_days": 10},
        "2024-02": {"throughput": 7, "cycle_time_days": 10},
        "2024-03": {"throughput": 10, "cycle_time_days": 10},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03"]
    result = window_standouts(sprints, data_bearing)
    # Both pairs have throughput improving by 3; the earlier pair wins.
    assert result["biggest_improvement"]["measure"] == "throughput"
    assert result["biggest_improvement"]["from_sprint"] == "2024-01"
    assert result["biggest_improvement"]["to_sprint"] == "2024-02"
    assert result["biggest_improvement"]["size"] == 3

    # Within the same pair, two measures tie: cycle_time_days improves by 3 and
    # throughput improves by 3. cycle_time_days comes first in the registry.
    sprints2 = {
        "2024-01": {"cycle_time_days": 10, "throughput": 5},
        "2024-02": {"cycle_time_days": 7, "throughput": 8},
        "2024-03": {"cycle_time_days": 7, "throughput": 8},
    }
    data_bearing2 = ["2024-01", "2024-02", "2024-03"]
    result2 = window_standouts(sprints2, data_bearing2)
    # cycle_time_days improves by 3 in the first pair; throughput also improves
    # by 3 in the same pair. cycle_time_days is earlier in the registry, so it wins.
    assert result2["biggest_improvement"]["measure"] == "cycle_time_days"
    assert result2["biggest_improvement"]["from_sprint"] == "2024-01"
    assert result2["biggest_improvement"]["to_sprint"] == "2024-02"


def test_movement_only_measures_never_appear_as_standouts():
    """AC6: biggest_improvement and worst_dip are computed only over measures
    that have a better direction; movement-only measures never appear."""
    # first_attempt_numerator has no better direction; even with a large step,
    # it never appears.
    sprints = {
        "2024-01": {"first_attempt_numerator": 1, "throughput": 4},
        "2024-02": {"first_attempt_numerator": 100, "throughput": 5},
        "2024-03": {"first_attempt_numerator": 50, "throughput": 3},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03"]
    result = window_standouts(sprints, data_bearing)
    assert result["biggest_improvement"]["measure"] == "throughput"
    assert result["worst_dip"]["measure"] == "throughput"


def test_standout_size_carries_unit_and_precision():
    """AC6: every standout's size carries the measure's unit and whole-number
    precision."""
    sprints = {
        "2024-01": {"cycle_time_days": 10},
        "2024-02": {"cycle_time_days": 7},
        "2024-03": {"cycle_time_days": 9},
    }
    data_bearing = ["2024-01", "2024-02", "2024-03"]
    result = window_standouts(sprints, data_bearing)
    assert result["biggest_improvement"]["unit"] == "days"
    assert result["biggest_improvement"]["precision"] == "whole"
    assert result["worst_dip"]["unit"] == "days"
    assert result["worst_dip"]["precision"] == "whole"
