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
    throughput, falls below) the threshold.
    """
    effective = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)

    return {
        "cycle_time_days": cycle_time > effective["cycle_time_days"],
        "lead_time_days": lead_time > effective["lead_time_days"],
        "throughput": throughput < effective["throughput"],
        "wip_violations": wip_violations > effective["wip_violations"],
        "blocked_aging_days": blocked_aging > effective["blocked_aging_days"],
        "escalation_rate_percent": escalation_rate > effective["escalation_rate_percent"],
    }


def _load_thresholds(source: str) -> dict[str, float]:
    """Parse the JSON object of metric thresholds the command was given."""
    raw = json.loads(source) if source.strip() else {}
    if not isinstance(raw, Mapping):
        raise TypeError("expected a JSON object of thresholds, keyed by metric name")
    return {str(key): float(value) for key, value in raw.items()}


def _flag(value: int, thresholds: Mapping[str, float] | None, metric: str) -> str:
    """Return ' \u26a0\ufe0f' when ``value`` exceeds the threshold for ``metric``, else ''.

    A ``None`` thresholds mapping means no thresholds are in effect, so no
    metric is flagged. The comparison is strict greater-than: meeting the
    threshold exactly is not a breach.
    """
    if thresholds is None:
        return ""
    threshold = thresholds.get(metric)
    if threshold is None:
        return ""
    return " \u26a0\ufe0f" if value > threshold else ""
