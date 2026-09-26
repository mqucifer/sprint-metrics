"""Pure metric calculations for the sprint-metrics package."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from sprint_metrics.card import Card, _as_cards


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


def _load_wip_limits(source: str) -> dict[str, int]:
    """Parse the JSON object of state names to WIP limits the command was given."""
    raw = json.loads(source) if source.strip() else {}
    if not isinstance(raw, Mapping):
        raise TypeError("expected a JSON object of WIP limits, keyed by state")
    return {str(state): int(limit) for state, limit in raw.items()}


ALL_METRICS: frozenset[str] = frozenset(
    {
        "cycle_time_days",
        "lead_time_days",
        "throughput",
        "wip_violations",
        "blocked_aging_days",
        "escalation_rate_percent",
    }
)
