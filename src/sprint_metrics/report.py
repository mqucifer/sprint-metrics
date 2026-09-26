"""Single-sprint formatters for the sprint-metrics package."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from sprint_metrics.card import Card, _as_cards
from sprint_metrics.metrics import (
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)
from sprint_metrics.thresholds import _flag, calculate_flags


def format_performance_table(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    prior_cards: Iterable[Card | Mapping[str, object]] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> str:
    """Render the crew performance metrics as a markdown table.

    When ``prior_cards`` is provided, a second row labelled Prior is appended
    after the Current row so the two periods can be compared at a glance, and a
    third row labelled Delta shows the signed change in each metric from the
    prior period to the current period.

    When ``thresholds`` is provided, a ⚠️ marker is appended to any metric cell
    in the Current row whose value exceeds its threshold (strict greater-than;
    meeting the threshold exactly is not a breach). The Prior and Delta rows are
    never flagged.
    """
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards, as_of)
    escalation_rate = calculate_escalation_rate(cards, escalations)
    sprint_label = as_of.isoformat() if as_of is not None else "Current"
    rows = [
        "| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate |",
        "|--------|------------|-----------|------------|----------------|---------------|-----------------|",
        f"| {sprint_label} | {cycle_time} days{_flag(cycle_time, thresholds, 'cycle_time_days')} "
        f"| {lead_time} days{_flag(lead_time, thresholds, 'lead_time_days')} "
        f"| {throughput}{_flag(throughput, thresholds, 'throughput')} "
        f"| {wip_violations}{_flag(wip_violations, thresholds, 'wip_violations')} "
        f"| {blocked_aging} days{_flag(blocked_aging, thresholds, 'blocked_aging_days')} "
        f"| {escalation_rate}%{_flag(escalation_rate, thresholds, 'escalation_rate_percent')} |",
    ]
    if prior_cards is not None:
        prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
        prior_throughput = calculate_throughput(prior_cards)
        prior_wip = calculate_wip_violations(prior_cards, wip_limits)
        prior_blocked = calculate_blocked_aging(prior_cards, as_of)
        prior_escalation = calculate_escalation_rate(prior_cards, escalations)
        rows.append(
            f"| Prior | {prior_cycle} days | {prior_lead} days | {prior_throughput} "
            f"| {prior_wip} | {prior_blocked} days | {prior_escalation}% |"
        )
        rows.append(
            f"| Delta | {_signed(cycle_time - prior_cycle)} days | {_signed(lead_time - prior_lead)} days "
            f"| {_signed(throughput - prior_throughput)} | {_signed(wip_violations - prior_wip)} "
            f"| {_signed(blocked_aging - prior_blocked)} days | {_signed(escalation_rate - prior_escalation)}% |"
        )
    return "\n".join(rows)


def _summary_counts(cards: Sequence[Card]) -> tuple[int, int, int]:
    """Count the cards standing in each state the standup summary reports.

    The three states are exclusive, so every card is counted once: completing a
    card settles it whatever else happened to it on the way, and a card held up
    is reported as blocked rather than as still in progress.
    """
    completed = in_progress = blocked = 0
    for card in cards:
        if card.is_completed:
            completed += 1
        elif card.blocked_since is not None:
            blocked += 1
        elif card.started is not None:
            in_progress += 1
    return completed, in_progress, blocked


def _summary_section(cards: Sequence[Card]) -> list[str]:
    """The standup-ready summary of how much work stands in each state."""
    completed, in_progress, blocked = _summary_counts(cards)
    return [
        "## Crew Performance Summary",
        "",
        f"- **Completed**: {completed}",
        f"- **In progress**: {in_progress}",
        f"- **Blocked**: {blocked}",
    ]


def _sprint_section(
    cards: Sequence[Card],
    wip_limits: Mapping[str, int] | None,
    escalations: int,
    as_of: date | None = None,
    prior_cards: Sequence[Card] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> list[str]:
    """The current sprint's delivery metrics.

    Only rendered when there are cards: with none, the metrics are all zero for
    want of data rather than because the sprint went that way.

    When ``prior_cards`` is provided, each metric line includes the prior
    sprint's value and the signed change from prior to current.

    When ``thresholds`` is provided, a ⚠️ marker is appended to any metric line
    whose value exceeds its threshold (strict greater-than; meeting the
    threshold exactly is not a breach).
    """
    if not cards:
        return ["No performance data available"]
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards, as_of)
    escalation_rate = calculate_escalation_rate(cards, escalations)

    if prior_cards is not None:
        prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
        prior_throughput = calculate_throughput(prior_cards)
        prior_wip = calculate_wip_violations(prior_cards, wip_limits)
        prior_blocked = calculate_blocked_aging(prior_cards, as_of)
        prior_escalation = calculate_escalation_rate(prior_cards, escalations)
        return [
            "## Current Sprint",
            "",
            f"- **Cycle time**: {cycle_time} days (was {prior_cycle} days, {_signed(cycle_time - prior_cycle)}){_flag(cycle_time, thresholds, 'cycle_time_days')}",
            f"- **Lead time**: {lead_time} days (was {prior_lead} days, {_signed(lead_time - prior_lead)}){_flag(lead_time, thresholds, 'lead_time_days')}",
            f"- **Throughput**: {throughput} (was {prior_throughput}, {_signed(throughput - prior_throughput)}){_flag(throughput, thresholds, 'throughput')}",
            f"- **WIP violations**: {wip_violations} (was {prior_wip}, {_signed(wip_violations - prior_wip)}){_flag(wip_violations, thresholds, 'wip_violations')}",
            f"- **Blocked aging**: {blocked_aging} days (was {prior_blocked} days, {_signed(blocked_aging - prior_blocked)}){_flag(blocked_aging, thresholds, 'blocked_aging_days')}",
            f"- **Escalation rate**: {escalation_rate}% (was {prior_escalation}%, {_signed(escalation_rate - prior_escalation)}){_flag(escalation_rate, thresholds, 'escalation_rate_percent')}",
        ]
    return [
        "## Current Sprint",
        "",
        f"- **Cycle time**: {cycle_time} days{_flag(cycle_time, thresholds, 'cycle_time_days')}",
        f"- **Lead time**: {lead_time} days{_flag(lead_time, thresholds, 'lead_time_days')}",
        f"- **Throughput**: {throughput} cards{_flag(throughput, thresholds, 'throughput')}",
        f"- **WIP violations**: {wip_violations}{_flag(wip_violations, thresholds, 'wip_violations')}",
        f"- **Blocked aging**: {blocked_aging} days{_flag(blocked_aging, thresholds, 'blocked_aging_days')}",
        f"- **Escalation rate**: {escalation_rate}%{_flag(escalation_rate, thresholds, 'escalation_rate_percent')}",
    ]


def format_markdown_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    prior_sprint: str | None = None,
    prior_cards: Sequence[Card] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> str:
    """Render the crew performance metrics as a markdown report for the standup issue.

    The report is written to be pasted straight into the standup issue, so it
    always opens with its heading and the date it covers, and always closes with
    the summary of work in each state — an empty sprint reports zeros rather
    than leaving the Scrum Master to explain a missing section.

    When ``prior_sprint`` and ``prior_cards`` are provided, a comparison section
    for the prior sprint is included before the current sprint section, and the
    current sprint's metrics show the prior value and signed change.

    When ``thresholds`` is provided, a ⚠️ marker is appended to any metric line
    whose value exceeds its threshold.
    """
    parsed = _as_cards(cards)
    report_date = as_of if as_of is not None else date.today()
    lines: list[str] = [
        "# Crew Performance Report",
        "",
        f"Report date: {report_date.isoformat()}",
    ]
    if prior_sprint is not None and prior_cards is not None:
        lines.append("")
        lines.extend(
            _prior_sprint_section(prior_cards, prior_sprint, wip_limits, escalations, as_of)
        )
    lines.append("")
    lines.extend(_sprint_section(parsed, wip_limits, escalations, as_of, prior_cards, thresholds))
    lines.append("")
    lines.extend(_summary_section(parsed))
    return "\n".join(lines)


def format_prometheus_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
) -> str:
    """Render the crew performance metrics in Prometheus text exposition format."""
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    return "\n".join(
        [
            f"sprint_cycle_time_days {cycle_time}",
            f"sprint_lead_time_days {lead_time}",
            f"sprint_throughput_cards {throughput}",
            f"sprint_wip_violations {wip_violations}",
            f"sprint_blocked_aging_days {blocked_aging}",
            f"sprint_escalation_rate_percent {escalation_rate}",
        ]
    )


def format_json_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> str:
    """Render the crew performance metrics as a JSON object."""
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    flags = calculate_flags(parsed, wip_limits, escalations, as_of, thresholds)
    report: dict[str, object] = {
        "api_version": API_VERSION,
        "cycle_time_days": cycle_time,
        "lead_time_days": lead_time,
        "throughput": throughput,
        "wip_violations": wip_violations,
        "blocked_aging_days": blocked_aging,
        "escalation_rate_percent": escalation_rate,
        "flags": flags,
    }
    if as_of is not None:
        report["sprint_date"] = as_of.isoformat()
    return json.dumps(report)


def _prior_sprint_section(
    cards: Sequence[Card],
    label: str,
    wip_limits: Mapping[str, int] | None,
    escalations: int,
    as_of: date | None = None,
) -> list[str]:
    """The prior sprint's delivery metrics, rendered as a comparison section.

    Only rendered when there are cards: with none, the metrics are all zero for
    want of data rather than because the sprint went that way.
    """
    if not cards:
        return ["No performance data available"]
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    return [
        f"## Prior Sprint {label}",
        "",
        f"- **Cycle time**: {cycle_time} days",
        f"- **Lead time**: {lead_time} days",
        f"- **Throughput**: {calculate_throughput(cards)} cards",
        f"- **WIP violations**: {calculate_wip_violations(cards, wip_limits)}",
        f"- **Blocked aging**: {calculate_blocked_aging(cards, as_of)} days",
        f"- **Escalation rate**: {calculate_escalation_rate(cards, escalations)}%",
    ]


def _signed(delta: int) -> str:
    """Format a signed change: a zero change is a bare ``0``, otherwise ``+N`` or ``-N``."""
    if delta == 0:
        return "0"
    return f"{delta:+d}"


API_VERSION = "1"
