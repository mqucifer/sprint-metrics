"""Crew performance command: report cycle time, lead time, throughput, and
WIP-limit violations for the current sprint."""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import sys
import threading
from collections.abc import Mapping, Sequence
from datetime import date

from sprint_metrics.card import Card, _as_cards, _load_cards
from sprint_metrics.metrics import (
    _load_wip_limits,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)
from sprint_metrics.report import (
    _summary_section,
    format_json_report,
    format_markdown_report,
    format_performance_table,
    format_prometheus_report,
)
from sprint_metrics.thresholds import _flag, _load_thresholds, calculate_flags


def _mean_days(values: Sequence[int]) -> int:
    """Average a set of day counts, to the nearest whole day. No values means 0."""
    if not values:
        return 0
    return round(sum(values) / len(values))


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
                    sprints, labels, wip_limits, args.escalations, sprint_date, thresholds
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


# Fixed default thresholds for flagging metric breaches in JSON output.
# These are not configurable; they represent the crew's standing expectations.
