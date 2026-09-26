"""Sprint-label and range parsing and per-sprint range formatters."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date

from sprint_metrics.card import Card, _as_cards
from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)
from sprint_metrics.report import API_VERSION, _summary_section
from sprint_metrics.thresholds import _flag, calculate_flags


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


def _parse_sprint_range(value: str) -> list[str]:
    """Parse an inclusive ``START..END`` sprint range into a list of ``YYYY-MM`` labels.

    Raises ``ValueError`` if the value is not in ``START..END`` form or if either
    endpoint is not a valid ``YYYY-MM`` label.
    """
    parts = value.split("..")
    if len(parts) != 2:
        raise ValueError(f"sprint range {value!r} is not in START..END format")
    start_label, end_label = parts
    start_year, start_month = _parse_sprint_label(start_label)
    end_year, end_month = _parse_sprint_label(end_label)
    if (start_year, start_month) > (end_year, end_month):
        raise ValueError(f"sprint range start {start_label!r} is after end {end_label!r}")
    labels: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        labels.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return labels


def _load_sprints(source: str) -> dict[str, list[Card]]:
    """Parse a JSON object keyed by sprint label, each value a list of cards.

    Raises ``TypeError`` if the top-level JSON value is not an object.
    """
    raw = json.loads(source) if source.strip() else {}
    if not isinstance(raw, dict):
        raise TypeError("expected a JSON object keyed by sprint label")
    sprints: dict[str, list[Card]] = {}
    for label, cards in raw.items():
        if not isinstance(cards, list):
            raise TypeError(f"sprint {label!r} must map to a JSON list of cards")
        sprints[str(label)] = _as_cards(cards)
    return sprints


def format_sprint_range_table(
    sprints: Mapping[str, list[Card]],
    labels: Sequence[str],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> str:
    """Render one table row per sprint label in ``labels``, in order.

    Each row uses the same WIP limits, escalation count, and reference date.

    When ``thresholds`` is provided, a ⚠️ marker is appended to any metric cell
    whose value exceeds its threshold (strict greater-than; meeting the
    threshold exactly is not a breach).
    """
    rows = [
        "| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate |",
        "|--------|------------|-----------|------------|----------------|---------------|-----------------|",
    ]
    for label in labels:
        cards = sprints[label]
        cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
        throughput = calculate_throughput(cards)
        wip_violations = calculate_wip_violations(cards, wip_limits)
        blocked_aging = calculate_blocked_aging(cards, as_of)
        escalation_rate = calculate_escalation_rate(cards, escalations)
        rows.append(
            f"| {label} | {cycle_time} days{_flag(cycle_time, thresholds, 'cycle_time_days')} "
            f"| {lead_time} days{_flag(lead_time, thresholds, 'lead_time_days')} "
            f"| {throughput}{_flag(throughput, thresholds, 'throughput')} "
            f"| {wip_violations}{_flag(wip_violations, thresholds, 'wip_violations')} "
            f"| {blocked_aging} days{_flag(blocked_aging, thresholds, 'blocked_aging_days')} "
            f"| {escalation_rate}%{_flag(escalation_rate, thresholds, 'escalation_rate_percent')} |"
        )
    return "\n".join(rows)


def format_sprint_range_json(
    sprints: Mapping[str, list[Card]],
    labels: Sequence[str],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> str:
    """Render one JSON object per sprint label in ``labels``, keyed by label, wrapped
    in a top-level object with ``api_version`` and a ``sprints`` key.

    Each value under ``sprints`` carries the same six metrics the table and
    single-sprint JSON reports produce, plus a flags object computed with the same
    thresholds as the single-sprint report, so a script can process the range without
    parsing a table. Each sprint also includes a ``prior`` key holding the six metrics
    computed from the immediately preceding sprint label in the range, or
    ``null`` for the first sprint, and a ``delta`` key holding the signed change
    in each metric from the prior period to the current period, or ``null`` for
    the first sprint.
    """
    per_sprint: dict[str, object] = {}
    for index, label in enumerate(labels):
        cards = sprints[label]
        cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
        sprint_metrics = {
            "cycle_time_days": cycle_time,
            "lead_time_days": lead_time,
            "throughput": calculate_throughput(cards),
            "wip_violations": calculate_wip_violations(cards, wip_limits),
            "blocked_aging_days": calculate_blocked_aging(cards, as_of),
            "escalation_rate_percent": calculate_escalation_rate(cards, escalations),
        }
        if index == 0:
            prior = None
            delta = None
        else:
            prior_label = labels[index - 1]
            prior_cards = sprints[prior_label]
            prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
            prior = {
                "cycle_time_days": prior_cycle,
                "lead_time_days": prior_lead,
                "throughput": calculate_throughput(prior_cards),
                "wip_violations": calculate_wip_violations(prior_cards, wip_limits),
                "blocked_aging_days": calculate_blocked_aging(prior_cards, as_of),
                "escalation_rate_percent": calculate_escalation_rate(prior_cards, escalations),
            }
            delta = {
                "cycle_time_days": sprint_metrics["cycle_time_days"] - prior["cycle_time_days"],
                "lead_time_days": sprint_metrics["lead_time_days"] - prior["lead_time_days"],
                "throughput": sprint_metrics["throughput"] - prior["throughput"],
                "wip_violations": sprint_metrics["wip_violations"] - prior["wip_violations"],
                "blocked_aging_days": sprint_metrics["blocked_aging_days"]
                - prior["blocked_aging_days"],
                "escalation_rate_percent": (
                    sprint_metrics["escalation_rate_percent"] - prior["escalation_rate_percent"]
                ),
            }
        per_sprint[label] = {
            **sprint_metrics,
            "flags": calculate_flags(cards, wip_limits, escalations, as_of, thresholds),
            "prior": prior,
            "delta": delta,
        }
    report: dict[str, object] = {
        "api_version": API_VERSION,
        "sprints": per_sprint,
    }
    return json.dumps(report)


def format_sprint_range_markdown(
    sprints: Mapping[str, list[Card]],
    labels: Sequence[str],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
) -> str:
    """Render one markdown section per sprint label in ``labels``, in order.

    The report opens with the same heading and report date as the single-sprint
    markdown report, then carries one ``## Sprint <label>`` section per sprint so
    a Scrum Master can paste a comparable record of past sprints into the
    standup issue. Each section shows the sprint's delivery metrics when it has
    cards, or ``No performance data available`` when it does not, and always
    closes with the summary of work in each state.
    """
    report_date = as_of if as_of is not None else date.today()
    lines: list[str] = [
        "# Crew Performance Report",
        "",
        f"Report date: {report_date.isoformat()}",
    ]
    for label in labels:
        cards = sprints[label]
        lines.append("")
        lines.append(f"## Sprint {label}")
        lines.append("")
        if not cards:
            lines.append("No performance data available")
        else:
            cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
            lines.append(f"- **Cycle time**: {cycle_time} days")
            lines.append(f"- **Lead time**: {lead_time} days")
            lines.append(f"- **Throughput**: {calculate_throughput(cards)} cards")
            lines.append(f"- **WIP violations**: {calculate_wip_violations(cards, wip_limits)}")
            lines.append(f"- **Blocked aging**: {calculate_blocked_aging(cards, as_of)} days")
            lines.append(f"- **Escalation rate**: {calculate_escalation_rate(cards, escalations)}%")
        lines.append("")
        lines.extend(_summary_section(cards))
    return "\n".join(lines)
