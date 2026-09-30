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
    calculate_failure_breakdown,
    calculate_first_attempt_rate,
    calculate_throughput,
    calculate_top_failure_causes,
    calculate_wip_violations,
)
from sprint_metrics.thresholds import DEFAULT_THRESHOLDS, _flag, _threshold_context, calculate_flags


def format_performance_table(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    prior_cards: Iterable[Card | Mapping[str, object]] | None = None,
    thresholds: Mapping[str, float] | None = None,
    metrics: frozenset[str] | None = None,
) -> str:
    """Render the crew performance metrics as a markdown table.

    When ``prior_cards`` is provided, a second row labelled Prior is appended
    after the Current row so the two periods can be compared at a glance, and a
    third row labelled Delta shows the signed change in each metric from the
    prior period to the current period.

    When ``thresholds`` is provided, a \u26a0\ufe0f marker is appended to any metric cell
    in the Current row whose value exceeds its threshold (strict greater-than;
    meeting the threshold exactly is not a breach). The Prior and Delta rows are
    never flagged.

    When ``metrics`` is provided, only the requested metric columns are emitted;
    the header, separator, and every data row use the same column set.
    """
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards, as_of)
    escalation_rate = calculate_escalation_rate(cards, escalations)
    first_attempt_rate = calculate_first_attempt_rate(cards)
    failure_breakdown = calculate_failure_breakdown(cards)
    sprint_label = as_of.isoformat() if as_of is not None else "Current"

    if metrics is not None:
        selected = [m for m in _CANONICAL_ORDER if m in metrics]
    else:
        selected = list(_CANONICAL_ORDER)

    headers = ["Sprint"] + [_METRIC_COLUMNS[m] for m in selected]
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "|" + "|".join("-" * (len(h) + 2) for h in headers) + "|"

    current_cells: dict[str, str] = {
        "cycle_time_days": f"{cycle_time} days{_flag(cycle_time, thresholds, 'cycle_time_days')}",
        "lead_time_days": f"{lead_time} days{_flag(lead_time, thresholds, 'lead_time_days')}",
        "throughput": f"{throughput}{_flag(throughput, thresholds, 'throughput')}",
        "wip_violations": f"{wip_violations}{_flag(wip_violations, thresholds, 'wip_violations')}",
        "blocked_aging_days": f"{blocked_aging} days{_flag(blocked_aging, thresholds, 'blocked_aging_days')}",
        "escalation_rate_percent": f"{escalation_rate}%{_flag(escalation_rate, thresholds, 'escalation_rate_percent')}",
        "first_attempt_rate_percent": f"{first_attempt_rate}%{_flag(first_attempt_rate, thresholds, 'first_attempt_rate_percent')}",
        "failure_breakdown": _format_failure_breakdown(failure_breakdown),
    }
    current_row = f"| {sprint_label} | " + " | ".join(current_cells[m] for m in selected) + " |"

    rows = [header_row, separator_row, current_row]

    if prior_cards is not None:
        prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
        prior_throughput = calculate_throughput(prior_cards)
        prior_wip = calculate_wip_violations(prior_cards, wip_limits)
        prior_blocked = calculate_blocked_aging(prior_cards, as_of)
        prior_escalation = calculate_escalation_rate(prior_cards, escalations)
        prior_first_attempt = calculate_first_attempt_rate(prior_cards)

        prior_cells: dict[str, str] = {
            "cycle_time_days": f"{prior_cycle} days",
            "lead_time_days": f"{prior_lead} days",
            "throughput": f"{prior_throughput}",
            "wip_violations": f"{prior_wip}",
            "blocked_aging_days": f"{prior_blocked} days",
            "escalation_rate_percent": f"{prior_escalation}%",
            "first_attempt_rate_percent": f"{prior_first_attempt}%",
            "failure_breakdown": "\u2014",
        }
        prior_row = "| Prior | " + " | ".join(prior_cells[m] for m in selected) + " |"

        delta_cells: dict[str, str] = {
            "cycle_time_days": f"{_signed(cycle_time - prior_cycle)} days",
            "lead_time_days": f"{_signed(lead_time - prior_lead)} days",
            "throughput": f"{_signed(throughput - prior_throughput)}",
            "wip_violations": f"{_signed(wip_violations - prior_wip)}",
            "blocked_aging_days": f"{_signed(blocked_aging - prior_blocked)} days",
            "escalation_rate_percent": f"{_signed(escalation_rate - prior_escalation)}%",
            "first_attempt_rate_percent": f"{_signed(first_attempt_rate - prior_first_attempt)}%",
            "failure_breakdown": "\u2014",
        }
        delta_row = "| Delta | " + " | ".join(delta_cells[m] for m in selected) + " |"

        rows.append(prior_row)
        rows.append(delta_row)

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
    metrics: frozenset[str] | None = None,
) -> list[str]:
    """The current sprint's delivery metrics.

    When cards is empty, emits 'No performance data available' followed by the
    first-attempt rate line (always 0%) so the standup report shows both.

    When ``prior_cards`` is provided, each metric line includes a directional
    arrow (\u2193, \u2191, or \u2192) between the current value and the parenthetical,
    the prior sprint's value, and the signed change from prior to current.

    When ``thresholds`` is provided, a \u26a0\ufe0f marker followed by a parenthetical
    naming the configured threshold is appended to any metric line whose value
    exceeds its threshold (strict greater-than; meeting the threshold exactly
    is not a breach).

    When ``metrics`` is provided, only the requested metric lines are emitted;
    the section heading is always present when cards exist.
    """
    if not cards:
        return ["No performance data available", "", "- **First-attempt rate**: 0%"]
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards, as_of)
    escalation_rate = calculate_escalation_rate(cards, escalations)
    first_attempt_rate = calculate_first_attempt_rate(cards)
    failure_breakdown = calculate_failure_breakdown(cards)

    if metrics is not None:
        selected = [m for m in _CANONICAL_ORDER if m in metrics]
    else:
        selected = list(_CANONICAL_ORDER)

    if prior_cards is not None:
        prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
        prior_throughput = calculate_throughput(prior_cards)
        prior_wip = calculate_wip_violations(prior_cards, wip_limits)
        prior_blocked = calculate_blocked_aging(prior_cards, as_of)
        prior_escalation = calculate_escalation_rate(prior_cards, escalations)
        prior_first_attempt = calculate_first_attempt_rate(prior_cards)
        lines: list[str] = ["## Current Sprint", ""]
        for metric in selected:
            if metric == "cycle_time_days":
                delta = cycle_time - prior_cycle
                lines.append(
                    f"- **Cycle time**: {cycle_time} days {_trend_arrow(delta)} "
                    f"(was {prior_cycle} days, {_signed(delta)})"
                    f"{_threshold_context(cycle_time, thresholds, 'cycle_time_days')}"
                )
            elif metric == "lead_time_days":
                delta = lead_time - prior_lead
                lines.append(
                    f"- **Lead time**: {lead_time} days {_trend_arrow(delta)} "
                    f"(was {prior_lead} days, {_signed(delta)})"
                    f"{_threshold_context(lead_time, thresholds, 'lead_time_days')}"
                )
            elif metric == "throughput":
                delta = throughput - prior_throughput
                lines.append(
                    f"- **Throughput**: {throughput} cards {_trend_arrow(delta)} "
                    f"(was {prior_throughput}, {_signed(delta)})"
                    f"{_threshold_context(throughput, thresholds, 'throughput')}"
                )
            elif metric == "wip_violations":
                delta = wip_violations - prior_wip
                lines.append(
                    f"- **WIP violations**: {wip_violations} {_trend_arrow(delta)} "
                    f"(was {prior_wip}, {_signed(delta)})"
                    f"{_threshold_context(wip_violations, thresholds, 'wip_violations')}"
                )
            elif metric == "blocked_aging_days":
                delta = blocked_aging - prior_blocked
                lines.append(
                    f"- **Blocked aging**: {blocked_aging} days {_trend_arrow(delta)} "
                    f"(was {prior_blocked} days, {_signed(delta)})"
                    f"{_threshold_context(blocked_aging, thresholds, 'blocked_aging_days')}"
                )
            elif metric == "escalation_rate_percent":
                delta = escalation_rate - prior_escalation
                lines.append(
                    f"- **Escalation rate**: {escalation_rate}% {_trend_arrow(delta)} "
                    f"(was {prior_escalation}%, {_signed(delta)})"
                    f"{_threshold_context(escalation_rate, thresholds, 'escalation_rate_percent')}"
                )
            elif metric == "first_attempt_rate_percent":
                delta = first_attempt_rate - prior_first_attempt
                lines.append(
                    f"- **First-attempt rate**: {first_attempt_rate}% {_trend_arrow(delta)} "
                    f"(was {prior_first_attempt}%, {_signed(delta)})"
                    f"{_threshold_context(first_attempt_rate, thresholds, 'first_attempt_rate_percent')}"
                )
        if "failure_breakdown" in selected and failure_breakdown:
            lines.append("")
            lines.append("Top failure causes")
            for cls, role, count in failure_breakdown:
                if role:
                    lines.append(f"- {count}\u00d7 {cls} ({role})")
                else:
                    lines.append(f"- {count}\u00d7 {cls}")
        return lines
    lines = ["## Current Sprint", ""]
    for metric in selected:
        if metric == "cycle_time_days":
            lines.append(
                f"- **Cycle time**: {cycle_time} days{_threshold_context(cycle_time, thresholds, 'cycle_time_days')}"
            )
        elif metric == "lead_time_days":
            lines.append(
                f"- **Lead time**: {lead_time} days{_threshold_context(lead_time, thresholds, 'lead_time_days')}"
            )
        elif metric == "throughput":
            lines.append(
                f"- **Throughput**: {throughput} cards{_threshold_context(throughput, thresholds, 'throughput')}"
            )
        elif metric == "wip_violations":
            lines.append(
                f"- **WIP violations**: {wip_violations}{_threshold_context(wip_violations, thresholds, 'wip_violations')}"
            )
        elif metric == "blocked_aging_days":
            lines.append(
                f"- **Blocked aging**: {blocked_aging} days{_threshold_context(blocked_aging, thresholds, 'blocked_aging_days')}"
            )
        elif metric == "escalation_rate_percent":
            lines.append(
                f"- **Escalation rate**: {escalation_rate}%{_threshold_context(escalation_rate, thresholds, 'escalation_rate_percent')}"
            )
        elif metric == "first_attempt_rate_percent":
            lines.append(
                f"- **First-attempt rate**: {first_attempt_rate}%{_threshold_context(first_attempt_rate, thresholds, 'first_attempt_rate_percent')}"
            )
    if "failure_breakdown" in selected and failure_breakdown:
        lines.append("")
        lines.append("Top failure causes")
        for cls, role, count in failure_breakdown:
            if role:
                lines.append(f"- {count}\u00d7 {cls} ({role})")
            else:
                lines.append(f"- {count}\u00d7 {cls}")
    return lines


def format_markdown_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    prior_sprint: str | None = None,
    prior_cards: Sequence[Card] | None = None,
    thresholds: Mapping[str, float] | None = None,
    metrics: frozenset[str] | None = None,
) -> str:
    """Render the crew performance metrics as a markdown report for the standup issue.

    The report is written to be pasted straight into the standup issue, so it
    always opens with its heading and the date it covers, and always closes with
    the summary of work in each state — an empty sprint reports zeros rather
    than leaving the Scrum Master to explain a missing section.

    Between the report date and the first section heading, a health summary
    shows whether any metric breaches its threshold: 'Status: All clear' when
    none do, or 'Status: Attention needed (N metrics breached)' followed by a
    bulleted list naming each breached metric with its value and threshold.
    When ``prior_sprint`` and ``prior_cards`` are provided, a 'Changed:' line
    names the metric with the largest absolute delta from the prior sprint.

    When ``prior_sprint`` and ``prior_cards`` are provided, a comparison section
    for the prior sprint is included before the current sprint section, and the
    current sprint's metrics show the prior value and signed change.

    When ``thresholds`` is provided, a ⚠️ marker is appended to any metric line
    whose value exceeds its threshold.

    When ``metrics`` is provided, only the requested metric lines are emitted in
    the sprint section; the heading, report date, and summary section are always
    present regardless of ``metrics``.
    """
    parsed = _as_cards(cards)
    report_date = as_of if as_of is not None else date.today()
    lines: list[str] = [
        "# Crew Performance Report",
        "",
        f"Report date: {report_date.isoformat()}",
    ]
    lines.extend(
        _health_summary_lines(parsed, wip_limits, escalations, as_of, thresholds, prior_cards)
    )
    if prior_sprint is not None and prior_cards is not None:
        lines.append("")
        lines.extend(
            _prior_sprint_section(prior_cards, prior_sprint, wip_limits, escalations, as_of)
        )
    lines.append("")
    lines.extend(
        _sprint_section(parsed, wip_limits, escalations, as_of, prior_cards, thresholds, metrics)
    )
    lines.append("")
    lines.extend(_summary_section(parsed))
    return "\n".join(lines)


def format_prometheus_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
    as_of: date | None = None,
    metrics: frozenset[str] | None = None,
) -> str:
    """Render the crew performance metrics in Prometheus text exposition format.

    When ``metrics`` is provided, only the requested metric lines are emitted,
    in canonical order.
    """
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    first_attempt_rate = calculate_first_attempt_rate(parsed)
    failure_breakdown = calculate_failure_breakdown(parsed)

    all_lines: list[tuple[str, str]] = [
        ("cycle_time_days", f"sprint_cycle_time_days {cycle_time}"),
        ("lead_time_days", f"sprint_lead_time_days {lead_time}"),
        ("throughput", f"sprint_throughput_cards {throughput}"),
        ("wip_violations", f"sprint_wip_violations {wip_violations}"),
        ("blocked_aging_days", f"sprint_blocked_aging_days {blocked_aging}"),
        ("escalation_rate_percent", f"sprint_escalation_rate_percent {escalation_rate}"),
        (
            "first_attempt_rate_percent",
            f"sprint_first_attempt_rate_percent {first_attempt_rate}",
        ),
    ]
    if metrics is not None:
        selected = [line for name, line in all_lines if name in metrics]
    else:
        selected = [line for _, line in all_lines]

    if metrics is None or "failure_breakdown" in metrics:
        for cls, role, count in failure_breakdown:
            selected.append(f'sprint_failure_count{{class="{cls}",role="{role}"}} {count}')

    return "\n".join(selected)


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
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed, as_of)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    first_attempt_rate = calculate_first_attempt_rate(parsed)
    failure_breakdown = calculate_failure_breakdown(parsed)
    top_causes = calculate_top_failure_causes(parsed)
    flags = calculate_flags(parsed, wip_limits, escalations, as_of, thresholds)

    all_metric_values: dict[str, object] = {
        "cycle_time_days": cycle_time,
        "lead_time_days": lead_time,
        "throughput": throughput,
        "wip_violations": wip_violations,
        "blocked_aging_days": blocked_aging,
        "escalation_rate_percent": escalation_rate,
        "first_attempt_rate_percent": first_attempt_rate,
        "failure_breakdown": [
            {"class": cls, "role": role, "count": count} for cls, role, count in failure_breakdown
        ],
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
        "top_failure_causes": top_causes,
        "flags": filtered_flags,
    }
    if as_of is not None:
        report["sprint_date"] = as_of.isoformat()

    if prior_cards is not None:
        prior_parsed = _as_cards(prior_cards)
        prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_parsed)
        prior_throughput = calculate_throughput(prior_parsed)
        prior_wip = calculate_wip_violations(prior_parsed, wip_limits)
        prior_blocked = calculate_blocked_aging(prior_parsed, as_of)
        prior_escalation = calculate_escalation_rate(prior_parsed, escalations)
        prior_first_attempt = calculate_first_attempt_rate(prior_parsed)
        prior_top_causes = calculate_top_failure_causes(prior_parsed)
        report["prior"] = {
            "cycle_time_days": prior_cycle,
            "lead_time_days": prior_lead,
            "throughput": prior_throughput,
            "wip_violations": prior_wip,
            "blocked_aging_days": prior_blocked,
            "escalation_rate_percent": prior_escalation,
            "first_attempt_rate_percent": prior_first_attempt,
            "top_failure_causes": prior_top_causes,
        }
        report["delta"] = {
            "cycle_time_days": cycle_time - prior_cycle,
            "lead_time_days": lead_time - prior_lead,
            "throughput": throughput - prior_throughput,
            "wip_violations": wip_violations - prior_wip,
            "blocked_aging_days": blocked_aging - prior_blocked,
            "escalation_rate_percent": escalation_rate - prior_escalation,
            "first_attempt_rate_percent": first_attempt_rate - prior_first_attempt,
        }

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
    first_attempt_rate = calculate_first_attempt_rate(cards)
    return [
        f"## Prior Sprint {label}",
        "",
        f"- **Cycle time**: {cycle_time} days",
        f"- **Lead time**: {lead_time} days",
        f"- **Throughput**: {calculate_throughput(cards)} cards",
        f"- **WIP violations**: {calculate_wip_violations(cards, wip_limits)}",
        f"- **Blocked aging**: {calculate_blocked_aging(cards, as_of)} days",
        f"- **Escalation rate**: {calculate_escalation_rate(cards, escalations)}%",
        f"- **First-attempt rate**: {first_attempt_rate}%",
    ]


def _signed(delta: int) -> str:
    """Format a signed change: a zero change is a bare ``0``, otherwise ``+N`` or ``-N``."""
    if delta == 0:
        return "0"
    return f"{delta:+d}"


API_VERSION = "1"


_METRIC_COLUMNS: dict[str, str] = {
    "cycle_time_days": "Cycle time",
    "lead_time_days": "Lead time",
    "throughput": "Throughput",
    "wip_violations": "WIP violations",
    "blocked_aging_days": "Blocked aging",
    "escalation_rate_percent": "Escalation rate",
    "first_attempt_rate_percent": "First attempt",
    "failure_breakdown": "Top causes",
}


_CANONICAL_ORDER: tuple[str, ...] = (
    "cycle_time_days",
    "lead_time_days",
    "throughput",
    "wip_violations",
    "blocked_aging_days",
    "escalation_rate_percent",
    "first_attempt_rate_percent",
    "failure_breakdown",
)


def _format_failure_breakdown(breakdown: list[tuple[str, str, int]]) -> str:
    """Render the failure breakdown as 'N\u00d7 class (role), \u2026' or '\u2014' when empty."""
    if not breakdown:
        return "\u2014"
    parts = []
    for cls, role, count in breakdown:
        if role:
            parts.append(f"{count}\u00d7 {cls} ({role})")
        else:
            parts.append(f"{count}\u00d7 {cls}")
    return ", ".join(parts)


def _trend_arrow(delta: int) -> str:
    """Return the directional arrow for a signed change: \u2193, \u2191, or \u2192."""
    if delta < 0:
        return "\u2193"
    if delta > 0:
        return "\u2191"
    return "\u2192"


_HEALTH_DISPLAY: dict[str, str] = {
    "cycle_time_days": "Cycle time",
    "lead_time_days": "Lead time",
    "throughput": "Throughput",
    "wip_violations": "WIP violations",
    "blocked_aging_days": "Blocked aging",
    "escalation_rate_percent": "Escalation rate",
    "first_attempt_rate_percent": "First attempt rate",
}

_LOWER_IS_BETTER: frozenset[str] = frozenset(
    (
        "cycle_time_days",
        "lead_time_days",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
    )
)


def _format_breached_metric(metric: str, value: int, threshold: float) -> str:
    """A single breached-metric bullet with value and threshold in the metric's unit."""
    name = _HEALTH_DISPLAY[metric]
    if metric in ("cycle_time_days", "lead_time_days", "blocked_aging_days"):
        return f"- {name}: {value} days (threshold {threshold:g} days)"
    if metric == "throughput":
        unit = "card" if threshold == 1 else "cards"
        return f"- {name}: {value} cards (threshold {threshold:g} {unit})"
    if metric == "wip_violations":
        return f"- {name}: {value} (threshold {threshold:g})"
    if metric in ("escalation_rate_percent", "first_attempt_rate_percent"):
        return f"- {name}: {value}% (threshold {threshold:g}%)"
    raise ValueError(f"unknown metric for health summary: {metric}")


def _health_summary_lines(
    cards: Sequence[Card],
    wip_limits: Mapping[str, int] | None,
    escalations: int,
    as_of: date | None,
    thresholds: Mapping[str, float] | None,
    prior_cards: Sequence[Card] | None = None,
) -> list[str]:
    """The health summary lines: a status line and, when metrics breach, their bullets.

    Returns an empty list when there are no cards (the 'No performance data
    available' section handles that case). Otherwise returns the status line
    followed by one bullet per breached metric, in canonical order.

    When ``prior_cards`` is provided, a 'Changed:' line naming the metric with
    the largest absolute delta from the prior sprint is appended after the
    status and any breached-metric bullets.

    When one or more cards are blocked or in progress, an 'Attention:' line is
    appended after the status, breached bullets, and Changed line (if any).
    """
    if not cards:
        return []
    flags = calculate_flags(cards, wip_limits, escalations, as_of, thresholds)
    effective = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    breached = [m for m in _CANONICAL_ORDER if m != "failure_breakdown" and flags.get(m)]
    if not breached:
        lines = ["Status: All clear"]
    else:
        cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
        throughput = calculate_throughput(cards)
        wip_violations = calculate_wip_violations(cards, wip_limits)
        blocked_aging = calculate_blocked_aging(cards, as_of)
        escalation_rate = calculate_escalation_rate(cards, escalations)
        first_attempt_rate = calculate_first_attempt_rate(cards)

        values: dict[str, int] = {
            "cycle_time_days": cycle_time,
            "lead_time_days": lead_time,
            "throughput": throughput,
            "wip_violations": wip_violations,
            "blocked_aging_days": blocked_aging,
            "escalation_rate_percent": escalation_rate,
            "first_attempt_rate_percent": first_attempt_rate,
        }

        lines = [f"Status: Attention needed ({len(breached)} metrics breached)"]
        for metric in breached:
            lines.append(_format_breached_metric(metric, values[metric], effective[metric]))
    if prior_cards is not None:
        lines.append(_changed_line(cards, prior_cards, wip_limits, escalations, as_of))
    attention = _attention_line(cards, as_of)
    if attention is not None:
        lines.append(attention)
    return lines


def _changed_line(
    cards: Sequence[Card],
    prior_cards: Sequence[Card],
    wip_limits: Mapping[str, int] | None,
    escalations: int,
    as_of: date | None,
) -> str:
    """The 'Changed:' line: names the metric with the largest absolute delta from the prior sprint.

    Ties in absolute magnitude are broken by canonical order. When all deltas
    are zero, returns 'Changed: No change'.
    """
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards, as_of)
    escalation_rate = calculate_escalation_rate(cards, escalations)
    first_attempt_rate = calculate_first_attempt_rate(cards)

    prior_cycle, prior_lead = calculate_cycle_time_and_lead_time(prior_cards)
    prior_throughput = calculate_throughput(prior_cards)
    prior_wip = calculate_wip_violations(prior_cards, wip_limits)
    prior_blocked = calculate_blocked_aging(prior_cards, as_of)
    prior_escalation = calculate_escalation_rate(prior_cards, escalations)
    prior_first_attempt = calculate_first_attempt_rate(prior_cards)

    deltas: dict[str, int] = {
        "cycle_time_days": cycle_time - prior_cycle,
        "lead_time_days": lead_time - prior_lead,
        "throughput": throughput - prior_throughput,
        "wip_violations": wip_violations - prior_wip,
        "blocked_aging_days": blocked_aging - prior_blocked,
        "escalation_rate_percent": escalation_rate - prior_escalation,
        "first_attempt_rate_percent": first_attempt_rate - prior_first_attempt,
    }

    best_metric: str | None = None
    best_abs: int = 0
    for metric in _CANONICAL_ORDER:
        if metric == "failure_breakdown":
            continue
        abs_delta = abs(deltas[metric])
        if abs_delta > best_abs:
            best_abs = abs_delta
            best_metric = metric

    if best_metric is None or best_abs == 0:
        return "Changed: No change"

    delta = deltas[best_metric]
    if best_metric in _LOWER_IS_BETTER:
        direction = "improved" if delta < 0 else "worsened"
    else:
        direction = "improved" if delta > 0 else "worsened"

    name = _HEALTH_DISPLAY[best_metric]
    unit = _changed_unit(best_metric, best_abs)
    if unit:
        return f"Changed: {name} {direction} by {best_abs} {unit}"
    return f"Changed: {name} {direction} by {best_abs}"


def _changed_unit(metric: str, magnitude: int) -> str:
    """The unit word for a changed-metric line, singular or plural as needed."""
    if metric in ("cycle_time_days", "lead_time_days", "blocked_aging_days"):
        return "days"
    if metric == "throughput":
        return "card" if magnitude == 1 else "cards"
    if metric == "wip_violations":
        return ""
    if metric in ("escalation_rate_percent", "first_attempt_rate_percent"):
        return "percent"
    return ""


def _attention_line(cards: Sequence[Card], as_of: date | None) -> str | None:
    """The 'Attention:' line naming blocked and in-progress card counts.

    Returns None when no card is blocked or in progress. The duration shown is
    the longest block duration among blocked cards. When ``as_of`` is None the
    reference date is today, matching the Blocked aging metric.
    """
    _, in_progress, blocked = _summary_counts(cards)
    if blocked == 0 and in_progress == 0:
        return None
    duration = ""
    if blocked > 0:
        reference = as_of if as_of is not None else date.today()
        durations = [
            (reference - card.blocked_since).days
            for card in cards
            if card.blocked_since is not None and not card.is_completed
        ]
        if durations:
            duration = f" ({max(durations)} days)"
    return f"Attention: {blocked} blocked{duration}, {in_progress} in progress"
