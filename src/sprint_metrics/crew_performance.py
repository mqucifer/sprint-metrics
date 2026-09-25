"""Crew performance command: report cycle time, lead time, throughput, and
WIP-limit violations for the current sprint."""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import sys
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Card:
    """A single card on the sprint board.

    ``started`` and ``completed`` are ``None`` while the card has not yet
    reached that point on the board.
    """

    created: date
    started: date | None = None
    completed: date | None = None
    blocked_since: date | None = None

    @property
    def is_completed(self) -> bool:
        """Whether the card has finished, and so counts towards the metrics."""
        return self.completed is not None

    @property
    def cycle_time(self) -> int:
        """Days from starting work to completing it, or 0 if either is missing."""
        if self.completed is None or self.started is None:
            return 0
        return (self.completed - self.started).days

    @property
    def lead_time(self) -> int:
        """Days from creation to completion, or 0 if the card is not complete."""
        if self.completed is None:
            return 0
        return (self.completed - self.created).days


def _parse_date(value: object, field: str) -> date | None:
    """Read an optional ISO-8601 date. Missing, null and empty all mean "not yet"."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO-8601 date string, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not an ISO-8601 date: {value!r}") from exc


def parse_card(raw: Mapping[str, object]) -> Card:
    """Build a ``Card`` from its serialised form."""
    created = _parse_date(raw.get("created"), "created")
    if created is None:
        raise ValueError("every card needs a 'created' date")
    return Card(
        created=created,
        started=_parse_date(raw.get("started"), "started"),
        completed=_parse_date(raw.get("completed"), "completed"),
        blocked_since=_parse_date(raw.get("blocked_since"), "blocked_since"),
    )


def _as_cards(cards: Iterable[Card | Mapping[str, object]]) -> list[Card]:
    """Accept cards either already parsed or still in their serialised form."""
    return [card if isinstance(card, Card) else parse_card(card) for card in cards]


def _mean_days(values: Sequence[int]) -> int:
    """Average a set of day counts, to the nearest whole day. No values means 0."""
    if not values:
        return 0
    return round(sum(values) / len(values))


def calculate_cycle_time_and_lead_time(
    cards: Iterable[Card | Mapping[str, object]],
) -> tuple[int, int]:
    """Return the sprint's average cycle time and lead time, in whole days.

    Only completed cards carry these metrics, so cards still in flight are
    ignored. A sprint with nothing completed reports 0 for both.
    """
    completed = [card for card in _as_cards(cards) if card.is_completed]
    return (
        _mean_days([card.cycle_time for card in completed]),
        _mean_days([card.lead_time for card in completed]),
    )


def calculate_throughput(cards: Iterable[Card | Mapping[str, object]]) -> int:
    """Return the number of completed cards in the sprint.

    Throughput is the count of cards that have reached the completed state.
    Cards still in flight do not count.
    """
    return sum(1 for card in _as_cards(cards) if card.is_completed)


def _state_windows(card: Card) -> dict[str, tuple[date, date | None]]:
    """When the card sat in each board state, as a half-open ``[entered, left)`` window.

    A ``None`` end means the card is in that state still. A card completed
    without ever being started went from To Do straight to Completed, so it
    never occupied In Progress.
    """
    windows: dict[str, tuple[date, date | None]] = {
        "To Do": (card.created, card.started or card.completed)
    }
    if card.started is not None:
        windows["In Progress"] = (card.started, card.completed)
    if card.completed is not None:
        windows["Completed"] = (card.completed, None)
    return windows


def _peak_occupancy(cards: Sequence[Card], state: str) -> int:
    """The most cards that sat in ``state`` at the same time during the sprint."""
    events: list[tuple[date, int]] = []
    for card in cards:
        window = _state_windows(card).get(state)
        if window is None:
            continue
        entered, left = window
        events.append((entered, 1))
        if left is not None:
            events.append((left, -1))

    peak = occupancy = 0
    # Departures sort ahead of arrivals on the same day: a card that leaves as
    # another arrives was never there at the same time.
    for _, change in sorted(events):
        occupancy += change
        peak = max(peak, occupancy)
    return peak


def calculate_wip_violations(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
) -> int:
    """Return the number of states whose WIP limit was breached this sprint.

    A state is in violation when more cards sat in it at the same time than its
    limit allows, at any point in the sprint — work that was started and
    finished before the report ran still crowded the board. States with no
    configured limit, and a sprint with no limits at all, cannot be violated.
    """
    if not wip_limits:
        return 0

    parsed = _as_cards(cards)
    breached = [
        state for state, limit in wip_limits.items() if _peak_occupancy(parsed, state) > limit
    ]
    return len(breached)


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


def _load_cards(source: str) -> list[Card]:
    """Parse the JSON list of cards the command was given."""
    raw = json.loads(source) if source.strip() else []
    if not isinstance(raw, list):
        raise TypeError("expected a JSON list of cards")
    return _as_cards(raw)


def _load_wip_limits(source: str) -> dict[str, int]:
    """Parse the JSON object of state names to WIP limits the command was given."""
    raw = json.loads(source) if source.strip() else {}
    if not isinstance(raw, Mapping):
        raise TypeError("expected a JSON object of WIP limits, keyed by state")
    return {str(state): int(limit) for state, limit in raw.items()}


def _read(handle) -> str:
    """Read a command-line file argument, closing it afterwards."""
    with handle:
        return handle.read()


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the crew performance command."""
    parser = argparse.ArgumentParser(
        prog="sprint-metrics",
        description=(
            "Report cycle time, lead time, throughput, and WIP-limit violations "
            "for the current sprint."
        ),
    )
    parser.add_argument(
        "cards",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="JSON file of sprint cards; reads stdin when omitted.",
    )
    parser.add_argument(
        "--wip-limits",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help='JSON file of WIP limits keyed by state, e.g. {"In Progress": 3}; '
        "without it no limits apply.",
    )
    parser.add_argument(
        "--escalations",
        type=int,
        default=0,
        metavar="N",
        help="Number of escalations to apply to each sprint in the range.",
    )
    parser.add_argument(
        "--sprint-date",
        type=str,
        default=None,
        metavar="DATE",
        help="ISO-8601 date to measure blocked aging against (default: today).",
    )
    parser.add_argument(
        "--sprint-range",
        type=str,
        default=None,
        metavar="START..END",
        help=(
            "Inclusive range of YYYY-MM sprint labels, e.g. 2024-01..2024-03. "
            "The cards file must be a JSON object keyed by sprint label."
        ),
    )
    parser.add_argument(
        "--prior-sprint",
        type=str,
        default=None,
        metavar="LABEL",
        help=(
            "A prior sprint label (YYYY-MM) to compare against in the markdown report. "
            "The cards file must be a JSON object keyed by sprint label."
        ),
    )
    parser.add_argument(
        "--prior",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help="JSON file of prior-period cards, shown as a second row in the default table.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output the report as markdown instead of the default table format.",
    )
    parser.add_argument(
        "--prometheus",
        action="store_true",
        help="Output the report in Prometheus text exposition format.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the report as a JSON object.",
    )
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Start an HTTP server that serves the metrics at /metrics for scraping.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9100,
        metavar="PORT",
        help="Port for the scrape server (default: 9100). Use 0 for an ephemeral port.",
    )
    parser.add_argument(
        "--thresholds",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help=(
            "JSON file of metric thresholds keyed by metric name, e.g. "
            '{"cycle_time_days": 3}; overrides the built-in defaults for the '
            "metrics it specifies."
        ),
    )
    args = parser.parse_args(argv)

    if args.sprint_date is not None:
        try:
            sprint_date = date.fromisoformat(args.sprint_date)
        except ValueError:
            print(
                f"sprint-metrics: --sprint-date is not an ISO-8601 date: {args.sprint_date!r}",
                file=sys.stderr,
            )
            return 2
    else:
        sprint_date = None

    if args.scrape:
        cards_path = args.cards.name if hasattr(args.cards, "name") else ""
        wip_limits_path = args.wip_limits.name if args.wip_limits is not None else None
        port = serve_metrics(cards_path, wip_limits_path, args.escalations, args.port)
        print(f"sprint-metrics: serving metrics at http://127.0.0.1:{port}/metrics", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            threading.Event().wait()
        return 0

    source = _read(args.cards)
    wip_source = _read(args.wip_limits) if args.wip_limits is not None else None
    thresholds_source = _read(args.thresholds) if args.thresholds is not None else None

    if args.sprint_range is not None:
        try:
            labels = _parse_sprint_range(args.sprint_range)
        except ValueError as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        try:
            sprints = _load_sprints(source)
            wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
            thresholds = (
                _load_thresholds(thresholds_source) if thresholds_source is not None else None
            )
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        missing = [label for label in labels if label not in sprints]
        if missing:
            print(
                f"sprint-metrics: no data for sprint {missing[0]}",
                file=sys.stderr,
            )
            return 2

        if args.json:
            print(
                format_sprint_range_json(
                    sprints, labels, wip_limits, args.escalations, sprint_date, thresholds
                )
            )
        elif args.markdown:
            print(
                format_sprint_range_markdown(
                    sprints, labels, wip_limits, args.escalations, sprint_date
                )
            )
        else:
            print(
                format_sprint_range_table(
                    sprints, labels, wip_limits, args.escalations, sprint_date
                )
            )
        return 0

    if args.prior_sprint is not None:
        try:
            sprints = _load_sprints(source)
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        if args.prior_sprint not in sprints:
            print(
                f"sprint-metrics: no data for prior sprint {args.prior_sprint!r}",
                file=sys.stderr,
            )
            return 2

        most_recent = max(sprints.keys())
        if args.prior_sprint == most_recent:
            print(
                f"sprint-metrics: prior sprint {args.prior_sprint!r} cannot be the most recent sprint",
                file=sys.stderr,
            )
            return 2

        try:
            wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
            thresholds = (
                _load_thresholds(thresholds_source) if thresholds_source is not None else None
            )
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        current_label = most_recent
        current_cards = sprints[current_label]
        prior_cards = sprints[args.prior_sprint]

        if args.markdown:
            print(
                format_markdown_report(
                    current_cards,
                    wip_limits,
                    args.escalations,
                    sprint_date,
                    prior_sprint=args.prior_sprint,
                    prior_cards=prior_cards,
                    thresholds=thresholds,
                )
            )
        elif args.json:
            print(format_json_report(current_cards, wip_limits, args.escalations, sprint_date))
        elif args.prometheus:
            print(
                format_prometheus_report(current_cards, wip_limits, args.escalations, sprint_date)
            )
        else:
            print(
                format_performance_table(current_cards, wip_limits, args.escalations, sprint_date)
            )
        return 0

    try:
        cards = _load_cards(source)
        wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
        thresholds = _load_thresholds(thresholds_source) if thresholds_source is not None else None
    except (TypeError, ValueError) as exc:
        print(f"sprint-metrics: {exc}", file=sys.stderr)
        return 2

    prior_cards = None
    if args.prior is not None:
        try:
            prior_cards = _load_cards(_read(args.prior))
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

    if args.prometheus:
        print(format_prometheus_report(cards, wip_limits, args.escalations, sprint_date))
    elif args.markdown:
        print(
            format_markdown_report(
                cards, wip_limits, args.escalations, sprint_date, thresholds=thresholds
            )
        )
    elif args.json:
        print(format_json_report(cards, wip_limits, args.escalations, sprint_date, thresholds))
    else:
        print(
            format_performance_table(
                cards,
                wip_limits,
                args.escalations,
                sprint_date,
                prior_cards=prior_cards,
                thresholds=thresholds,
            )
        )
    return 0


def calculate_blocked_aging(
    cards: Iterable[Card | Mapping[str, object]],
    as_of: date | None = None,
) -> int:
    """Return the maximum number of days any card has been blocked in the sprint.

    A card is considered blocked if it has a ``blocked_since`` date and has not
    yet been completed. The aging is measured from ``blocked_since`` to the
    card's completion date (if completed) or to ``as_of`` (if still blocked).
    When ``as_of`` is ``None`` the reference date is today.
    Cards that are not blocked or have no ``blocked_since`` date are ignored.
    """
    reference = as_of if as_of is not None else date.today()
    parsed = _as_cards(cards)
    max_aging = 0
    for card in parsed:
        if card.blocked_since is None:
            continue
        if card.completed is not None:
            aging = (card.completed - card.blocked_since).days
        else:
            aging = (reference - card.blocked_since).days
        max_aging = max(max_aging, aging)
    return max_aging


def calculate_escalation_rate(
    cards: Iterable[Card | Mapping[str, object]],
    escalations: int = 0,
) -> int:
    """Return the escalation rate as a percentage (0-100).

    The rate is the number of escalations divided by the number of completed
    cards, expressed as a whole-number percentage. When no cards are completed
    the rate is 0.
    """
    completed = sum(1 for card in _as_cards(cards) if card.is_completed)
    if completed == 0:
        return 0
    return round(escalations / completed * 100)


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


def serve_metrics(
    cards_path: str,
    wip_limits_path: str | None = None,
    escalations: int = 0,
    port: int = 9100,
) -> int:
    """Start an HTTP server that serves the current sprint metrics at /metrics.

    The cards file is re-read on every request so that changes to the board are
    reflected without a restart. Returns the port the server is listening on.
    """

    class MetricsHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return

            try:
                with open(cards_path) as f:
                    cards = _load_cards(f.read())
                wip_limits = None
                if wip_limits_path is not None:
                    with open(wip_limits_path) as f:
                        wip_limits = _load_wip_limits(f.read())
            except (TypeError, ValueError, OSError) as exc:
                error_body = f"sprint-metrics: {exc}"
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(error_body)))
                self.end_headers()
                self.wfile.write(error_body.encode())
                return

            body = format_prometheus_report(cards, wip_limits, escalations)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), MetricsHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return actual_port


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
) -> str:
    """Render one table row per sprint label in ``labels``, in order.

    Each row uses the same WIP limits, escalation count, and reference date.
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
            f"| {label} | {cycle_time} days | {lead_time} days | {throughput} "
            f"| {wip_violations} | {blocked_aging} days | {escalation_rate}% |"
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
    """Render one JSON object per sprint label in ``labels``, keyed by label.

    Each value carries the same six metrics the table and single-sprint JSON
    reports produce, plus a flags object computed with the same thresholds as
    the single-sprint report, so a script can process the range without parsing
    a table. Each sprint also includes a ``prior`` key holding the six metrics
    computed from the immediately preceding sprint label in the range, or
    ``null`` for the first sprint, and a ``delta`` key holding the signed change
    in each metric from the prior period to the current period, or ``null`` for
    the first sprint.
    """
    report: dict[str, object] = {}
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
        report[label] = {
            **sprint_metrics,
            "flags": calculate_flags(cards, wip_limits, escalations, as_of, thresholds),
            "prior": prior,
            "delta": delta,
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
    """Return ' ⚠️' when ``value`` exceeds the threshold for ``metric``, else ''.

    A ``None`` thresholds mapping means no thresholds are in effect, so no
    metric is flagged. The comparison is strict greater-than: meeting the
    threshold exactly is not a breach.
    """
    if thresholds is None:
        return ""
    threshold = thresholds.get(metric)
    if threshold is None:
        return ""
    return " ⚠️" if value > threshold else ""
