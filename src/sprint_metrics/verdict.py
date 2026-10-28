"""The measure registry and the window verdict: each scalar measure's better direction, unit, and precision."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sprint_metrics.metrics import _cost_flat

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
    "change_failure_count": ("lower", "count", "whole"),
    "change_failure_rate_percent": ("lower", "percent", "whole"),
    "mean_time_to_recovery_minutes": ("lower", "minutes", "whole"),
    "model_minutes_middle": (None, "minutes", "whole"),
    "model_minutes_total": (None, "minutes", "whole"),
    "input_tokens_middle": (None, "count", "whole"),
    "input_tokens_total": (None, "count", "whole"),
    "output_tokens_middle": (None, "count", "whole"),
    "output_tokens_total": (None, "count", "whole"),
}

# Measures that are derived from another measure in the registry (the same
# quantity in a different unit) and therefore excluded from the standouts
# computation, so the same step is not counted twice.
_DERIVED_MEASURES: frozenset[str] = frozenset({"cycle_time_minutes", "lead_time_minutes"})


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


def window_standouts(
    sprints: Mapping[str, Mapping[str, object]],
    data_bearing: Sequence[str],
    registry: Mapping[str, tuple[str | None, str, str]] = MEASURE_REGISTRY,
) -> dict[str, object]:
    """The window's standouts: biggest improvement, worst dip, turns, and the too-short flag.

    Computes the largest single-step improvement and the largest single-step dip
    between consecutive data-bearing sprints, judged in the measure's own unit,
    over measures that have a better direction. A turn is a sprint where a
    measure moved one way from the previous data-bearing sprint and the other
    way into the next. A window with fewer than three data-bearing sprints is
    flagged too short for a trend.

    ``sprints`` maps each sprint label to its measure values (``None`` when
    missing) and ``data_bearing`` is the ordered list of sprint labels that
    carried events; a gap sprint is bridged, not read as zero. Ties are broken
    by the earlier sprint pair, then the measure earlier in the registry order.
    """
    too_short = len(data_bearing) < 3
    if len(data_bearing) < 2:
        return {
            "biggest_improvement": None,
            "worst_dip": None,
            "turns": [],
            "too_short": too_short,
        }

    # Build the list of steps between consecutive data-bearing sprints.
    steps: list[tuple[str, str, dict[str, int]]] = []
    for i in range(len(data_bearing) - 1):
        from_label = data_bearing[i]
        to_label = data_bearing[i + 1]
        from_values = sprints[from_label]
        to_values = sprints[to_label]
        step: dict[str, int] = {}
        for measure in registry:
            if measure in _DERIVED_MEASURES:
                continue
            from_val = from_values.get(measure)
            to_val = to_values.get(measure)
            if from_val is None or to_val is None:
                continue
            step[measure] = to_val - from_val
        steps.append((from_label, to_label, step))

    # Find the biggest improvement and worst dip.
    best_improvement: dict[str, object] | None = None
    best_dip: dict[str, object] | None = None

    for from_label, to_label, step in steps:
        for measure in registry:
            if measure in _DERIVED_MEASURES:
                continue
            if measure not in step:
                continue
            better = registry[measure][0]
            if better is None:
                continue
            _, unit, precision = registry[measure]
            delta = step[measure]
            if delta == 0:
                continue
            is_improvement = (better == "lower" and delta < 0) or (
                better == "higher" and delta > 0
            )
            is_dip = (better == "lower" and delta > 0) or (better == "higher" and delta < 0)
            size = abs(delta)
            if is_improvement and (
                best_improvement is None or size > best_improvement["size"]
            ):
                best_improvement = {
                    "measure": measure,
                    "from_sprint": from_label,
                    "to_sprint": to_label,
                    "size": size,
                    "unit": unit,
                    "precision": precision,
                }
            if is_dip and (best_dip is None or size > best_dip["size"]):
                best_dip = {
                    "measure": measure,
                    "from_sprint": from_label,
                    "to_sprint": to_label,
                    "size": size,
                    "unit": unit,
                    "precision": precision,
                }

    # Find turns: a sprint where a measure moved one way into it and the other
    # way out of it (both steps non-zero and opposite direction). Only measures
    # with a better direction can turn.
    turns: list[dict[str, str]] = []
    if len(data_bearing) >= 3:
        for i in range(1, len(data_bearing) - 1):
            sprint_label = data_bearing[i]
            prev_step = steps[i - 1][2]
            next_step = steps[i][2]
            for measure in registry:
                if measure in _DERIVED_MEASURES:
                    continue
                if registry[measure][0] is None:
                    continue
                if measure not in prev_step or measure not in next_step:
                    continue
                in_delta = prev_step[measure]
                out_delta = next_step[measure]
                if in_delta * out_delta < 0:
                    turns.append({"sprint": sprint_label, "measure": measure})

    return {
        "biggest_improvement": best_improvement,
        "worst_dip": best_dip,
        "turns": turns,
        "too_short": too_short,
    }


def window_verdicts(
    sprints: Mapping[str, Mapping[str, object]],
    data_bearing: Sequence[str],
    registry: Mapping[str, tuple[str | None, str, str]] = MEASURE_REGISTRY,
) -> dict[str, dict[str, object] | None]:
    """The per-measure verdict across a window of sprints.

    Judges the window's first data-bearing sprint against its last, per
    measure, purely from the measure registry. ``sprints`` maps each sprint
    label to its measure values — one key per registry measure, the value
    ``None`` when the measure is missing for that sprint — and ``data_bearing``
    is the ordered list of sprint labels that carried events: a gap sprint,
    not in the list, is skipped, not read as zero.

    Every registry measure gets exactly one entry, keyed by the measure's name
    (the non-scalar items get none): an object carrying the verdict (better,
    worse or flat — or up, down or flat for a measure with no better
    direction), the two reference sprint labels, both reference values, the
    measure's unit, and its precision. The entry is null when the measure's
    value is missing in either reference sprint, or the window has fewer than
    two data-bearing sprints.
    """
    verdicts: dict[str, dict[str, object] | None] = {measure: None for measure in registry}
    if len(data_bearing) < 2:
        return verdicts
    first_label, last_label = data_bearing[0], data_bearing[-1]
    first = sprints[first_label]
    last = sprints[last_label]
    for measure in registry:
        first_value = first.get(measure)
        last_value = last.get(measure)
        if first_value is None or last_value is None:
            continue
        _, unit, precision = registry[measure]
        verdicts[measure] = {
            "verdict": verdict(measure, first_value, last_value, registry),
            "first_sprint": first_label,
            "last_sprint": last_label,
            "first_value": first_value,
            "last_value": last_value,
            "unit": unit,
            "precision": precision,
        }
    return verdicts


def _attach_range_verdict(result: dict, labels: list[str], has_events: set[str]) -> None:
    """Attach the per-measure window verdict to the range's window object.

    The window judges its first data-bearing sprint against its last, per
    registry measure, so a gap sprint (no events) is skipped, not read as zero.
    Each entry names both reference sprints and their values, with the unit and
    precision; an entry is null when the measure's value is missing in either
    reference sprint, or the window has fewer than two data-bearing sprints.
    """
    data_bearing = [label for label in labels if label in has_events]
    flat: dict[str, dict[str, object]] = {}
    for label in labels:
        entry = result["sprints"][label]
        values = dict(entry)
        values.update(_cost_flat(entry.get("cost")))
        flat[label] = values
    result["window"]["verdicts"] = window_verdicts(flat, data_bearing, MEASURE_REGISTRY)


_RANGE_VERDICT_DESCRIPTION = (
    "The response also carries a verdicts "
    "object with one entry per registry measure: it judges the window's "
    "first and last data-bearing sprint (a gap sprint is skipped, not "
    "read as zero) against each measure's better direction — better, "
    "worse or flat, or up, down or flat for a measure with no better "
    "direction — each entry naming both reference sprints and their "
    "values, with the unit and the precision; an entry reads null when "
    "the measure's value is missing in either reference sprint, or the "
    "window has fewer than two data-bearing sprints. "
)
