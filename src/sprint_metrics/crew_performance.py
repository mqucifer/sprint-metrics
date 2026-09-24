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
) -> str:
    """Render the crew performance metrics as a markdown table."""
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards)
    escalation_rate = calculate_escalation_rate(cards, escalations)
    return "\n".join(
        [
            "| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate |",
            "|--------|------------|-----------|------------|----------------|---------------|-----------------|",
            f"| Current | {cycle_time} days | {lead_time} days | {throughput} | {wip_violations} | {blocked_aging} days | {escalation_rate}% |",
        ]
    )


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
        help="Number of escalations in the current sprint.",
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
    args = parser.parse_args(argv)

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

    try:
        cards = _load_cards(source)
        wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
    except (TypeError, ValueError) as exc:
        print(f"sprint-metrics: {exc}", file=sys.stderr)
        return 2

    if args.prometheus:
        print(format_prometheus_report(cards, wip_limits, args.escalations))
    elif args.markdown:
        print(format_markdown_report(cards, wip_limits, args.escalations))
    elif args.json:
        print(format_json_report(cards, wip_limits, args.escalations))
    else:
        print(format_performance_table(cards, wip_limits, args.escalations))
    return 0


def calculate_blocked_aging(cards: Iterable[Card | Mapping[str, object]]) -> int:
    """Return the maximum number of days any card has been blocked in the sprint.

    A card is considered blocked if it has a ``blocked_since`` date and has not
    yet been completed. The aging is measured from ``blocked_since`` to the
    card's completion date (if completed) or to today (if still blocked).
    Cards that are not blocked or have no ``blocked_since`` date are ignored.
    """
    parsed = _as_cards(cards)
    max_aging = 0
    for card in parsed:
        if card.blocked_since is None:
            continue
        if card.completed is not None:
            aging = (card.completed - card.blocked_since).days
        else:
            aging = (date.today() - card.blocked_since).days
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
) -> list[str]:
    """The current sprint's delivery metrics.

    Only rendered when there are cards: with none, the metrics are all zero for
    want of data rather than because the sprint went that way.
    """
    if not cards:
        return ["No performance data available"]
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    return [
        "## Current Sprint",
        "",
        f"- **Cycle time**: {cycle_time} days",
        f"- **Lead time**: {lead_time} days",
        f"- **Throughput**: {calculate_throughput(cards)} cards",
        f"- **WIP violations**: {calculate_wip_violations(cards, wip_limits)}",
        f"- **Blocked aging**: {calculate_blocked_aging(cards)} days",
        f"- **Escalation rate**: {calculate_escalation_rate(cards, escalations)}%",
    ]


def format_markdown_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
) -> str:
    """Render the crew performance metrics as a markdown report for the standup issue.

    The report is written to be pasted straight into the standup issue, so it
    always opens with its heading and the date it covers, and always closes with
    the summary of work in each state — an empty sprint reports zeros rather
    than leaving the Scrum Master to explain a missing section.
    """
    parsed = _as_cards(cards)
    return "\n".join(
        [
            "# Crew Performance Report",
            "",
            f"Report date: {date.today().isoformat()}",
            "",
            *_sprint_section(parsed, wip_limits, escalations),
            "",
            *_summary_section(parsed),
        ]
    )


def format_prometheus_report(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
    escalations: int = 0,
) -> str:
    """Render the crew performance metrics in Prometheus text exposition format."""
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed)
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
) -> str:
    """Render the crew performance metrics as a JSON object."""
    parsed = _as_cards(cards)
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(parsed)
    throughput = calculate_throughput(parsed)
    wip_violations = calculate_wip_violations(parsed, wip_limits)
    blocked_aging = calculate_blocked_aging(parsed)
    escalation_rate = calculate_escalation_rate(parsed, escalations)
    return json.dumps(
        {
            "cycle_time_days": cycle_time,
            "lead_time_days": lead_time,
            "throughput": throughput,
            "wip_violations": wip_violations,
            "blocked_aging_days": blocked_aging,
            "escalation_rate_percent": escalation_rate,
        }
    )


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
