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
        "first_attempt_rate_percent",
        "failure_breakdown",
    }
)


def calculate_first_attempt_rate(cards: Iterable[Card | Mapping[str, object]]) -> int:
    """Return the percentage of completed cards that succeeded on the first attempt.

    A card succeeded on its first attempt when its ``attempts`` field is 1.
    Cards still in flight are ignored. When no cards are completed the rate is 0.
    """
    completed = [card for card in _as_cards(cards) if card.is_completed]
    if not completed:
        return 0
    first_attempt = sum(1 for card in completed if card.attempts == 1)
    return round(100 * first_attempt / len(completed))


def calculate_failure_breakdown(
    cards: Iterable[Card | Mapping[str, object]],
) -> list[tuple[str, str, int]]:
    """Return the failure causes grouped by (class, role), sorted by count descending.

    Only completed cards with ``attempts > 1`` contribute to the breakdown.
    Ties in count preserve first-encounter order (stable sort). When no completed
    card has attempts greater than 1 the result is an empty list.
    """
    completed = [card for card in _as_cards(cards) if card.is_completed and card.attempts > 1]
    if not completed:
        return []
    counts: dict[tuple[str, str], int] = {}
    for card in completed:
        key = (card.failure_class or "", card.failure_role or "")
        counts[key] = counts.get(key, 0) + 1
    return [
        (cls, role, count)
        for (cls, role), count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def calculate_top_failure_causes(cards: Iterable[Card | Mapping[str, object]]) -> dict[str, int]:
    """Return the top 3 failure causes among completed cards, as a dict mapping cause to count.

    Only completed cards with a non-None failure_class contribute. Ties in count are
    broken alphabetically. Returns an empty dict when no completed card has a failure_class.
    """
    completed = [
        card for card in _as_cards(cards) if card.is_completed and card.failure_class is not None
    ]
    if not completed:
        return {}
    counts: dict[str, int] = {}
    for card in completed:
        key = card.failure_class
        counts[key] = counts.get(key, 0) + 1
    sorted_items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return dict(sorted_items[:3])


def wip_violation_details(
    cards: Iterable[Card | Mapping[str, object]],
    wip_limits: Mapping[str, int] | None = None,
) -> list[tuple[str, int, int]]:
    """Return the breached states with their peak occupancy and configured limit.

    Returns a list of (state_name, peak_occupancy, configured_limit) tuples, one
    per state whose peak exceeded its limit, in the iteration order of
    ``wip_limits``. Returns an empty list when no state is breached or
    ``wip_limits`` is None or empty.
    """
    if not wip_limits:
        return []
    parsed = _as_cards(cards)
    details: list[tuple[str, int, int]] = []
    for state, limit in wip_limits.items():
        peak = _peak_occupancy(parsed, state)
        if peak > limit:
            details.append((state, peak, limit))
    return details


def blocked_aging_detail(
    cards: Iterable[Card | Mapping[str, object]],
    as_of: date | None = None,
) -> list[tuple[date, date]]:
    """Return the (created, blocked_since) dates of cards producing the maximum blocked aging.

    Computes each blocked card's aging the same way ``calculate_blocked_aging``
    does: completed cards use their completion date, in-flight cards use
    ``as_of`` (or today). Returns a list of (created, blocked_since) tuples for
    every card at the maximum (ties included). Returns an empty list when no
    card is blocked or the maximum aging is 0.
    """
    reference = as_of if as_of is not None else date.today()
    parsed = _as_cards(cards)
    agings: list[tuple[int, date, date]] = []
    for card in parsed:
        if card.blocked_since is None:
            continue
        if card.completed is not None:
            aging = (card.completed - card.blocked_since).days
        else:
            aging = (reference - card.blocked_since).days
        agings.append((aging, card.created, card.blocked_since))
    if not agings:
        return []
    max_aging = max(a for a, _, _ in agings)
    if max_aging == 0:
        return []
    return [
        (created, blocked_since) for aging, created, blocked_since in agings if aging == max_aging
    ]
