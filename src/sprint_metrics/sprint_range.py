"""Sprint-label and range parsing and per-sprint range formatters."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date

from sprint_metrics.card import Card
from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_cycle_time_minutes,
    calculate_failure_breakdown,
    calculate_first_attempt_rate,
    calculate_lead_time_minutes,
    calculate_superseded_breakdown,
    calculate_superseded_count,
    calculate_superseded_points,
    calculate_throughput,
    calculate_top_failure_causes,
    calculate_wip_violations,
)
from sprint_metrics.report import API_VERSION
from sprint_metrics.thresholds import calculate_flags


def _parse_sprint_label(label: str) -> tuple[int, int]:
    """Parse a ``YYYY-MM`` sprint label into ``(year, month)``.

    Raises ``ValueError`` if the label is not a valid four-digit year and
    two-digit month.
    """
    parts = label.split("-")
    if len(parts) != 2:
        raise ValueError(f"sprint label {label!r} is not in YYYY-MM format")
    year_str, month_str = parts
    if len(year_str) != 4 or not year_str.isdigit():
        raise ValueError(f"sprint label {label!r} has an invalid year component")
    if len(month_str) != 2 or not month_str.isdigit():
        raise ValueError(f"sprint label {label!r} has an invalid month component")
    year = int(year_str)
    month = int(month_str)
    if month < 1 or month > 12:
        raise ValueError(f"sprint label {label!r} has an invalid month: {month}")
    return year, month


def format_sprint_range_json(
    sprints: Mapping[str, list[Card]],
    labels: Sequence[str],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    thresholds: Mapping[str, float] | None = None,
    metrics: frozenset[str] | None = None,
    sprint_escalations: Mapping[str, int] | None = None,
) -> str:
    """Render one JSON object per sprint label in ``labels``, keyed by label, wrapped
    in a top-level object with ``api_version`` and a ``sprints`` key.

    Each value under ``sprints`` carries the sprint's metrics plus a flags object
    computed against the built-in default thresholds. Each sprint also includes a ``prior`` key holding the six metrics
    computed from the immediately preceding sprint label in the range, or
    ``null`` for the first sprint, and a ``delta`` key holding the signed change
    in each metric from the prior period to the current period, or ``null`` for
    the first sprint.

    When ``metrics`` is a non-None frozenset, only the named metric keys are
    included in each sprint entry, its prior, its delta, and its flags.

    When ``sprint_escalations`` is provided, each sprint uses its own escalation
    count from that mapping instead of the flat ``escalations`` value.
    """
    from sprint_metrics.metrics import (
        calculate_first_attempt_counts,
        calculate_points_delivered,
    )

    def _esc_for(label: str) -> int:
        if sprint_escalations is not None:
            return sprint_escalations.get(label, 0)
        return escalations

    per_sprint: dict[str, object] = {}
    for index, label in enumerate(labels):
        cards = sprints[label]
        esc = _esc_for(label)
        cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
        cycle_time_min = calculate_cycle_time_minutes(cards)
        lead_time_min = calculate_lead_time_minutes(cards)
        sprint_metrics = {
            "cycle_time_days": cycle_time,
            "lead_time_days": lead_time,
            "throughput": calculate_throughput(cards),
            "points_delivered": calculate_points_delivered(cards),
            "wip_violations": calculate_wip_violations(cards, wip_limits),
            "blocked_aging_days": calculate_blocked_aging(cards, as_of),
            "first_attempt_rate_percent": calculate_first_attempt_rate(cards),
            "first_attempt_numerator": calculate_first_attempt_counts(cards)[0],
            "first_attempt_denominator": calculate_first_attempt_counts(cards)[1],
            "superseded_count": calculate_superseded_count(cards),
            "superseded_points": calculate_superseded_points(cards),
            "superseded_breakdown": calculate_superseded_breakdown(cards),
            "cycle_time_minutes": cycle_time_min,
            "lead_time_minutes": lead_time_min,
        }
        if index == 0:
            prior = None
            delta = None
        else:
            prior_label = labels[index - 1]
            prior_cards = sprints[prior_label]
            prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
            prior_cycle_min = calculate_cycle_time_minutes(prior_cards)
            prior_lead_min = calculate_lead_time_minutes(prior_cards)
            prior_superseded_count = calculate_superseded_count(prior_cards)
            prior_superseded_points = calculate_superseded_points(prior_cards)
            prior_superseded_breakdown = calculate_superseded_breakdown(prior_cards)
            prior = {
                "cycle_time_days": prior_cycle,
                "lead_time_days": prior_lead,
                "throughput": calculate_throughput(prior_cards),
                "points_delivered": calculate_points_delivered(prior_cards),
                "wip_violations": calculate_wip_violations(prior_cards, wip_limits),
                "blocked_aging_days": calculate_blocked_aging(prior_cards, as_of),
                "first_attempt_rate_percent": calculate_first_attempt_rate(prior_cards),
                "first_attempt_numerator": calculate_first_attempt_counts(prior_cards)[0],
                "first_attempt_denominator": calculate_first_attempt_counts(prior_cards)[1],
                "superseded_count": prior_superseded_count,
                "superseded_points": prior_superseded_points,
                "superseded_breakdown": prior_superseded_breakdown,
                "cycle_time_minutes": prior_cycle_min,
                "lead_time_minutes": prior_lead_min,
            }
            sup_count = calculate_superseded_count(cards)
            sup_points = calculate_superseded_points(cards)
            sup_breakdown = calculate_superseded_breakdown(cards)
            delta = {
                "cycle_time_days": sprint_metrics["cycle_time_days"] - prior["cycle_time_days"],
                "lead_time_days": sprint_metrics["lead_time_days"] - prior["lead_time_days"],
                "throughput": sprint_metrics["throughput"] - prior["throughput"],
                "points_delivered": sprint_metrics["points_delivered"] - prior["points_delivered"],
                "wip_violations": sprint_metrics["wip_violations"] - prior["wip_violations"],
                "blocked_aging_days": calculate_blocked_aging(cards, as_of)
                - prior["blocked_aging_days"],
                "first_attempt_rate_percent": (
                    sprint_metrics["first_attempt_rate_percent"]
                    - prior["first_attempt_rate_percent"]
                ),
                "first_attempt_numerator": (
                    sprint_metrics["first_attempt_numerator"] - prior["first_attempt_numerator"]
                ),
                "first_attempt_denominator": (
                    sprint_metrics["first_attempt_denominator"] - prior["first_attempt_denominator"]
                ),
                "superseded_count": sup_count - prior_superseded_count,
                "superseded_points": sup_points - prior_superseded_points,
                "superseded_breakdown": sum(sup_breakdown.values())
                - sum(prior_superseded_breakdown.values()),
                "cycle_time_minutes": (
                    cycle_time_min - prior_cycle_min
                    if cycle_time_min is not None and prior_cycle_min is not None
                    else None
                ),
                "lead_time_minutes": (
                    lead_time_min - prior_lead_min
                    if lead_time_min is not None and prior_lead_min is not None
                    else None
                ),
            }
        flags = calculate_flags(cards, wip_limits, esc, as_of, thresholds)
        if metrics is not None:
            sprint_metrics = {k: v for k, v in sprint_metrics.items() if k in metrics}
            if prior is not None:
                prior = {k: v for k, v in prior.items() if k in metrics}
            if delta is not None:
                delta = {k: v for k, v in delta.items() if k in metrics}
            flags = {k: flags.get(k, False) for k in metrics}
        per_sprint[label] = {
            **sprint_metrics,
            "failure_breakdown": [
                {"class": cls, "role": role, "count": count}
                for cls, role, count in calculate_failure_breakdown(cards)
            ],
            "top_failure_causes": [
                {"class": cls, "role": role, "count": count}
                for cls, role, count in calculate_top_failure_causes(cards)
            ],
            "flags": flags,
            "prior": prior,
            "delta": delta,
        }
    report: dict[str, object] = {
        "api_version": API_VERSION,
        "sprints": per_sprint,
    }
    return json.dumps(report)
