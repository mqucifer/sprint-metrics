"""Tests for the measure registry and the window verdict in sprint_metrics.verdict."""

import pytest

from sprint_metrics.verdict import MEASURE_REGISTRY, verdict


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
