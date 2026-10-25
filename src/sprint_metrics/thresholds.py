"""Threshold defaults, flag calculation, and threshold loading for sprint-metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from sprint_metrics.card import Card, _as_cards
from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_cycle_time_minutes,
    calculate_escalation_rate,
    calculate_first_attempt_rate,
    calculate_lead_time_minutes,
    calculate_throughput,
    calculate_wip_violations,
)

# Fixed default thresholds for flagging metric breaches in JSON output.
# These are not configurable; they represent the crew's standing expectations.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "cycle_time_days": 5,
    "lead_time_days": 7,
    "cycle_time_minutes": 7200,
    "lead_time_minutes": 10080,
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
    cycle_time_minutes_val = calculate_cycle_time_minutes(parsed)
    lead_time_minutes_val = calculate_lead_time_minutes(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    first_attempt_rate = calculate_first_attempt_rate(parsed)

    return {
        "cycle_time_days": cycle_time > effective["cycle_time_days"],
        "lead_time_days": lead_time > effective["lead_time_days"],
        "cycle_time_minutes": (
            cycle_time_minutes_val is not None
            and cycle_time_minutes_val > effective["cycle_time_minutes"]
        ),
        "lead_time_minutes": (
            lead_time_minutes_val is not None
            and lead_time_minutes_val > effective["lead_time_minutes"]
        ),
        "throughput": throughput < effective["throughput"],
        "wip_violations": wip_violations > effective["wip_violations"],
        "blocked_aging_days": blocked_aging > effective["blocked_aging_days"],
        "escalation_rate_percent": escalation_rate > effective["escalation_rate_percent"],
        "first_attempt_rate_percent": first_attempt_rate < effective["first_attempt_rate_percent"],
    }
