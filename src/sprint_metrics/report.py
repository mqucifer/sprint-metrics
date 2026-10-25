"""Single-sprint formatters for the sprint-metrics package."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date

from sprint_metrics.card import Card, _as_cards
from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_cycle_time_minutes,
    calculate_escalation_rate,
    calculate_failure_breakdown,
    calculate_first_attempt_counts,
    calculate_first_attempt_rate,
    calculate_lead_time_minutes,
    calculate_points_delivered,
    calculate_superseded_breakdown,
    calculate_superseded_count,
    calculate_superseded_points,
    calculate_throughput,
    calculate_top_failure_causes,
    calculate_wip_violations,
)
from sprint_metrics.thresholds import calculate_flags


def format_json_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    thresholds: Mapping[str, float] | None = None,
    metrics: frozenset[str] | None = None,
    prior_cards: Iterable[Card | Mapping[str, object]] | None = None,
) -> str:
    """Render the crew performance metrics as a JSON object.

    When ``prior_cards`` is provided, the response includes a ``prior`` object
    with the metrics computed for the prior period and a ``delta`` object
    with the signed change (current minus prior) for each metric.
    """
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    cycle_time_minutes = calculate_cycle_time_minutes(parsed)
    lead_time_minutes = calculate_lead_time_minutes(parsed)
    throughput = calculate_throughput(parsed)
    points_delivered = calculate_points_delivered(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    first_attempt_rate = calculate_first_attempt_rate(parsed)
    first_attempt_num, first_attempt_den = calculate_first_attempt_counts(parsed)
    failure_breakdown = calculate_failure_breakdown(parsed)
    top_causes = calculate_top_failure_causes(parsed)
    superseded_count = calculate_superseded_count(parsed)
    superseded_points = calculate_superseded_points(parsed)
    superseded_breakdown = calculate_superseded_breakdown(parsed)
    flags = calculate_flags(parsed, wip_limits, escalations, as_of, thresholds)

    all_metric_values: dict[str, object] = {
        "cycle_time_days": cycle_time,
        "lead_time_days": lead_time,
        "cycle_time_minutes": cycle_time_minutes,
        "lead_time_minutes": lead_time_minutes,
        "throughput": throughput,
        "points_delivered": points_delivered,
        "wip_violations": wip_violations,
        "blocked_aging_days": blocked_aging,
        "escalation_rate_percent": escalation_rate,
        "escalation_count": escalations,
        "first_attempt_rate_percent": first_attempt_rate,
        "first_attempt_numerator": first_attempt_num,
        "first_attempt_denominator": first_attempt_den,
        "failure_breakdown": [
            {"class": cls, "role": role, "count": count} for cls, role, count in failure_breakdown
        ],
        "superseded_count": superseded_count,
        "superseded_points": superseded_points,
        "superseded_breakdown": superseded_breakdown,
    }
    if metrics is not None:
        metric_values = {k: v for k, v in all_metric_values.items() if k in metrics}
        filtered_flags = {k: v for k, v in flags.items() if k in metrics}
    else:
        metric_values = all_metric_values
        filtered_flags = flags

    report: dict[str, object] = {
        "api_version": API_VERSION,
        **metric_values,
        "top_failure_causes": [
            {"class": cls, "role": role, "count": count} for cls, role, count in top_causes
        ],
        "flags": filtered_flags,
    }
    if as_of is not None:
        report["sprint_date"] = as_of.isoformat()

    if prior_cards is not None:
        prior_parsed = _as_cards(prior_cards)
        prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_parsed)
        prior_cycle_minutes = calculate_cycle_time_minutes(prior_parsed)
        prior_lead_minutes = calculate_lead_time_minutes(prior_parsed)
        prior_throughput = calculate_throughput(prior_parsed)
        prior_wip = calculate_wip_violations(prior_parsed, wip_limits)
        prior_blocked = calculate_blocked_aging(prior_parsed, as_of)
        prior_escalation = calculate_escalation_rate(prior_parsed, escalations)
        prior_first_attempt = calculate_first_attempt_rate(prior_parsed)
        prior_top_causes = calculate_top_failure_causes(prior_parsed)
        prior_superseded_count = calculate_superseded_count(prior_parsed)
        prior_superseded_points = calculate_superseded_points(prior_parsed)
        prior_superseded_breakdown = calculate_superseded_breakdown(prior_parsed)
        report["prior"] = {
            "cycle_time_days": prior_cycle,
            "lead_time_days": prior_lead,
            "cycle_time_minutes": prior_cycle_minutes,
            "lead_time_minutes": prior_lead_minutes,
            "throughput": prior_throughput,
            "wip_violations": prior_wip,
            "blocked_aging_days": prior_blocked,
            "escalation_rate_percent": prior_escalation,
            "first_attempt_rate_percent": prior_first_attempt,
            "top_failure_causes": [
                {"class": cls, "role": role, "count": count}
                for cls, role, count in prior_top_causes
            ],
            "superseded_count": prior_superseded_count,
            "superseded_points": prior_superseded_points,
            "superseded_breakdown": prior_superseded_breakdown,
        }
        report["delta"] = {
            "cycle_time_days": cycle_time - prior_cycle,
            "lead_time_days": lead_time - prior_lead,
            "cycle_time_minutes": (
                None
                if cycle_time_minutes is None or prior_cycle_minutes is None
                else cycle_time_minutes - prior_cycle_minutes
            ),
            "lead_time_minutes": (
                None
                if lead_time_minutes is None or prior_lead_minutes is None
                else lead_time_minutes - prior_lead_minutes
            ),
            "throughput": throughput - prior_throughput,
            "wip_violations": wip_violations - prior_wip,
            "blocked_aging_days": blocked_aging - prior_blocked,
            "escalation_rate_percent": escalation_rate - prior_escalation,
            "first_attempt_rate_percent": first_attempt_rate - prior_first_attempt,
            "superseded_count": superseded_count - prior_superseded_count,
            "superseded_points": superseded_points - prior_superseded_points,
            "superseded_breakdown": sum(superseded_breakdown.values())
            - sum(prior_superseded_breakdown.values()),
        }

    return json.dumps(report)


API_VERSION = "2"


_METRIC_COLUMNS: dict[str, str] = {
    "cycle_time_days": "Cycle time",
    "lead_time_days": "Lead time",
    "cycle_time_minutes": "Cycle time (min)",
    "lead_time_minutes": "Lead time (min)",
    "throughput": "Throughput",
    "points_delivered": "Points delivered",
    "wip_violations": "WIP violations",
    "blocked_aging_days": "Blocked aging",
    "escalation_rate_percent": "Escalation rate",
    "escalation_count": "Escalation count",
    "first_attempt_rate_percent": "First attempt",
    "first_attempt_numerator": "First-attempt numerator",
    "first_attempt_denominator": "First-attempt denominator",
    "failure_breakdown": "Top causes",
    "superseded_count": "Superseded",
    "superseded_points": "Superseded points",
    "superseded_breakdown": "Superseded breakdown",
    "model_minutes_middle": "Model minutes (middle)",
    "model_minutes_total": "Model minutes (total)",
    "input_tokens_middle": "Input tokens (middle)",
    "input_tokens_total": "Input tokens (total)",
    "output_tokens_middle": "Output tokens (middle)",
    "output_tokens_total": "Output tokens (total)",
    "cached_input_percent": "Cached input percent",
    "reasoning_output_percent": "Reasoning output percent",
}
