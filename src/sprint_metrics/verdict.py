"""The measure registry and the window verdict: each scalar measure's better direction, unit, and precision."""

from __future__ import annotations

from collections.abc import Mapping

# Each entry names a measure's better direction — "lower", "higher", or None
# when the measure has no better direction (the first-attempt counts and the
# cost measures only move, they do not improve or worsen) — its unit, and its
# precision. Only the scalar measures a /range sprint entry carries appear
# here; the non-scalar items (failure_breakdown, top_failure_causes,
# superseded_breakdown, story_costs) carry no entry.
MEASURE_REGISTRY: Mapping[str, tuple[str | None, str, str]] = {
    "cycle_time_days": ("lower", "days", "whole"),
    "lead_time_days": ("lower", "days", "whole"),
    "cycle_time_minutes": ("lower", "minutes", "whole"),
    "lead_time_minutes": ("lower", "minutes", "whole"),
    "throughput": ("higher", "count", "whole"),
    "points_delivered": ("higher", "points", "whole"),
    "wip_violations": ("lower", "count", "whole"),
    "blocked_aging_days": ("lower", "days", "whole"),
    "first_attempt_rate_percent": ("higher", "percent", "whole"),
    "first_attempt_numerator": (None, "count", "whole"),
    "first_attempt_denominator": (None, "count", "whole"),
    "superseded_count": ("lower", "count", "whole"),
    "superseded_points": ("lower", "points", "whole"),
    "model_minutes_middle": (None, "minutes", "whole"),
    "model_minutes_total": (None, "minutes", "whole"),
    "input_tokens_middle": (None, "count", "whole"),
    "input_tokens_total": (None, "count", "whole"),
    "output_tokens_middle": (None, "count", "whole"),
    "output_tokens_total": (None, "count", "whole"),
}


def verdict(
    measure: str,
    first: int,
    last: int,
    registry: Mapping[str, tuple[str | None, str, str]] = MEASURE_REGISTRY,
) -> str:
    """Judge a first value against a last, purely from the measure's registry entry.

    A measure registered with a better direction ("lower" or "higher") carries
    a quality verdict: "better", "worse", or "flat" when the values are equal.
    A measure registered with no better direction carries movement only: "up",
    "down", or "flat" — never "better" or "worse". The entry's unit and
    precision do not affect the verdict; only the (measure, better-direction)
    pair does, so a new measure needs only a registry entry. Raises
    ``ValueError`` when the measure is not in the registry.
    """
    try:
        better = registry[measure][0]
    except KeyError:
        raise ValueError(f"unknown measure: {measure!r}") from None
    if first == last:
        return "flat"
    up = last > first
    if better is None:
        return "up" if up else "down"
    if better == "lower":
        return "worse" if up else "better"
    return "better" if up else "worse"
