"""Crew performance command: report cycle time, lead time, throughput, and
WIP-limit violations for the current sprint."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sprint_metrics.card import Card
from sprint_metrics.cli import main  # noqa: F401
from sprint_metrics.metrics import (  # noqa: F401
    _load_wip_limits,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)
from sprint_metrics.report import (  # noqa: F401
    format_json_report,
    format_markdown_report,
    format_performance_table,
    format_prometheus_report,
)
from sprint_metrics.serve import serve_metrics  # noqa: F401
from sprint_metrics.sprint_range import (  # noqa: F401
    _load_sprints,
    _parse_sprint_range,
    format_sprint_range_json,
    format_sprint_range_markdown,
    format_sprint_range_table,
)
from sprint_metrics.thresholds import _load_thresholds, calculate_flags  # noqa: F401


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
