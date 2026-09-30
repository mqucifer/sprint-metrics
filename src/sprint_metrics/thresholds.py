"""Threshold defaults, flag calculation, and threshold loading for sprint-metrics."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date

from sprint_metrics.card import Card, _as_cards
from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_first_attempt_rate,
    calculate_throughput,
    calculate_wip_violations,
)

# Fixed default thresholds for flagging metric breaches in JSON output.
# These are not configurable; they represent the crew's standing expectations.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "cycle_time_days": 5,
    "lead_time_days": 7,
    "throughput": 1,
    "wip_violations": 0,
    "blocked_aging_days": 5,
    "escalation_rate_percent": 10,
    "first_attempt_rate_percent": 80,
}


def calculate_flags(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, bool]:
    """Return a dict mapping each metric name to whether it breaches its threshold.

    The thresholds are the user-supplied ``thresholds`` merged over
    ``DEFAULT_THRESHOLDS``: a metric the user did not specify falls back to its
    default. A metric is flagged as breached when its value exceeds (or, for
    throughput and first_attempt_rate_percent, falls below) the threshold.
    """
    effective = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    first_attempt_rate = calculate_first_attempt_rate(parsed)

    return {
        "cycle_time_days": cycle_time > effective["cycle_time_days"],
        "lead_time_days": lead_time > effective["lead_time_days"],
        "throughput": throughput < effective["throughput"],
        "wip_violations": wip_violations > effective["wip_violations"],
        "blocked_aging_days": blocked_aging > effective["blocked_aging_days"],
        "escalation_rate_percent": escalation_rate > effective["escalation_rate_percent"],
        "first_attempt_rate_percent": first_attempt_rate < effective["first_attempt_rate_percent"],
    }


def _load_thresholds(source: str) -> dict[str, float]:
    """Parse the JSON object of metric thresholds the command was given."""
    raw = json.loads(source) if source.strip() else {}
    if not isinstance(raw, Mapping):
        raise TypeError("expected a JSON object of thresholds, keyed by metric name")
    return {str(key): float(value) for key, value in raw.items()}


def _is_breached(value: int, threshold: float, metric: str) -> bool:
    """Whether value breaches threshold for the given metric.

    For metrics where lower is worse (throughput, first_attempt_rate_percent)
    the breach is when value is strictly less than the threshold; for all
    others it is when value is strictly greater.
    """
    if metric in ("throughput", "first_attempt_rate_percent"):
        return value < threshold
    return value > threshold


def _threshold_display(metric: str, threshold: float) -> str:
    """The threshold value formatted with its display unit."""
    if metric in ("cycle_time_days", "lead_time_days", "blocked_aging_days"):
        return f"{threshold:g} days"
    if metric in ("escalation_rate_percent", "first_attempt_rate_percent"):
        return f"{threshold:g}%"
    return f"{threshold:g}"


def _threshold_context(value: int, thresholds: Mapping[str, float] | None, metric: str) -> str:
    """Return ' \u26a0\ufe0f (threshold: <value><unit>)' when the metric breaches, else ''.

    Same breach logic as _flag, but includes the threshold value with the
    metric's display unit in a parenthetical after the marker. Used in
    markdown output where the reader benefits from seeing the target.
    """
    if thresholds is None:
        return ""
    threshold = thresholds.get(metric)
    if threshold is None:
        return ""
    if not _is_breached(value, threshold, metric):
        return ""
    return f" \u26a0\ufe0f (threshold: {_threshold_display(metric, threshold)})"


def _flag(value: int, thresholds: Mapping[str, float] | None, metric: str) -> str:
    """Return ' \u26a0\ufe0f' when the metric breaches its threshold, else ''.

    A ``None`` thresholds mapping means no thresholds are in effect, so no
    metric is flagged. For metrics where lower is worse (throughput,
    first_attempt_rate_percent) the flag fires when value is strictly less
    than the threshold; for all others it fires when value is strictly
    greater.
    """
    if thresholds is None:
        return ""
    threshold = thresholds.get(metric)
    if threshold is None:
        return ""
    return " \u26a0\ufe0f" if _is_breached(value, threshold, metric) else ""
