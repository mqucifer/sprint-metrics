"""The sprint's working-time answer: the minutes the crew's sessions ran, per step of a story's pipeline.

Working time is derived from the rows already stored, with no new intake fields:
a session window runs from a story's 'started' row to its next terminal row
('finished', 'attempt_failed', or 'returned'), and a story's working time is the
sum of its windows. The 'attempt_failed' and 'returned' rows mark the step
boundary (the step is the role sent on that row), so a rework session is
labeled by the step it is reworking — the same step labels the rework answer
uses. A blocked interval within a window is not working time: the crew's clock
does not run while the story is blocked. A session not re-sent as 'started' is
invisible to working time and shows as idle instead (the fidelity bound, named
in docs/metrics.md). Windows are whole minutes; a sprint with no closed session
window reads null, matching the minute-based metrics' null behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

_TERMINAL = ("finished", "attempt_failed", "returned")


def _blocked_seconds(
    blocked: list[datetime], unblocked: list[datetime], window_start: datetime, window_end: datetime
) -> float:
    """Seconds a story was blocked within a window, pairing each blocked row with the next unblocked.

    Each blocked row is paired with the unblocked row that follows it (the rows
    arrive in event order). A pair whose unblocked row falls after the window's
    terminal row is clamped to the terminal, so a still-blocked story does not
    count past the point where its session ended.
    """
    total = 0.0
    for index, block_start in enumerate(blocked):
        if block_start < window_start or block_start > window_end:
            continue
        block_end = unblocked[index] if index < len(unblocked) else window_end
        end = min(block_end, window_end)
        start = max(block_start, window_start)
        if end > start:
            total += (end - start).total_seconds()
    return total


def calculate_working_time(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]],
) -> dict | None:
    """The sprint's working-time answer: per-step session minutes and the sprint total.

    ``events_by_card`` maps each card_id to its ordered
    (event_type, event_time, failure_role) rows for the 'started', 'finished',
    'attempt_failed', 'returned', 'blocked', and 'unblocked' rows, in event
    order. A session window runs from a 'started' row to the story's next
    terminal row ('finished', 'attempt_failed', or 'returned'); its minutes are
    the span minus any blocked interval within it, rounded to whole minutes.

    The step a window belongs to is the role sent on its terminal row when that
    row is an 'attempt_failed' or 'returned' row (the step boundary), or, for a
    window closed by 'finished', the role of the most recent preceding boundary
    — the step the rework session is reworking — or null when no such boundary
    was sent. ``per_step`` carries one entry per session window, in story and
    event order, so a sprint with two windows (an initial session and a rework
    session) carries both minutes; ``total`` is their sum. ``None`` when the
    sprint holds no closed session window, so a sprint whose cards carry only
    date-level fields, or no events at all, reads as no data, not zero.
    """
    per_step: list[dict] = []
    total = 0
    for events in events_by_card.values():
        open_window: tuple[datetime, str | None] | None = None
        last_boundary_role: str | None = None
        blocked: list[datetime] = []
        unblocked: list[datetime] = []
        for event_type, event_time, role in events:
            if event_type == "started":
                open_window = (event_time, last_boundary_role)
                blocked = []
                unblocked = []
            elif event_type == "blocked":
                if open_window is not None:
                    blocked.append(event_time)
            elif event_type == "unblocked":
                if open_window is not None:
                    unblocked.append(event_time)
            elif event_type in _TERMINAL:
                if open_window is not None:
                    window_start, preceding_role = open_window
                    window_end = event_time
                    step = preceding_role if event_type == "finished" else role
                    seconds = (window_end - window_start).total_seconds()
                    blocked_seconds = _blocked_seconds(blocked, unblocked, window_start, window_end)
                    minutes = round((seconds - blocked_seconds) / 60)
                    if minutes < 0:
                        minutes = 0
                    per_step.append({"step": step, "minutes": minutes})
                    total += minutes
                    open_window = None
                if event_type in ("attempt_failed", "returned"):
                    last_boundary_role = role
    if not per_step:
        return None
    return {"per_step": per_step, "total": total}


def working_time_total(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]],
) -> int | None:
    """The sprint's working-time total in whole minutes, or None when no closed session window is held.

    The same total the /range working-time answer carries, answered on its own
    for /trend and the prior/delta figures.
    """
    answer = calculate_working_time(events_by_card)
    return answer["total"] if answer is not None else None


def _card_total_minutes(
    events: list[tuple[str, datetime, str | None]],
) -> int:
    """Total working time in whole minutes for a single card's ordered event rows."""
    total = 0
    open_window: datetime | None = None
    blocked: list[datetime] = []
    unblocked: list[datetime] = []
    for event_type, event_time, _role in events:
        if event_type == "started":
            open_window = event_time
            blocked = []
            unblocked = []
        elif event_type == "blocked":
            if open_window is not None:
                blocked.append(event_time)
        elif event_type == "unblocked":
            if open_window is not None:
                unblocked.append(event_time)
        elif event_type in _TERMINAL:
            if open_window is not None:
                seconds = (event_time - open_window).total_seconds()
                blocked_seconds = _blocked_seconds(blocked, unblocked, open_window, event_time)
                minutes = round((seconds - blocked_seconds) / 60)
                if minutes < 0:
                    minutes = 0
                total += minutes
                open_window = None
    return total


def calculate_cost_by_kind(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]],
    kinds: Mapping[str, str | None],
) -> dict | None:
    """The sprint's working-time cost by story kind: addition and change, in whole minutes.

    ``events_by_card`` maps each card_id to its ordered
    (event_type, event_time, failure_role) rows (the same shape the working-time
    answer uses). ``kinds`` maps each card_id to its story kind string, or None
    when the stored rows carry no kind. The answer carries both keys (addition
    and change), each the sum of the working-time minutes of the stories of that
    kind in the sprint. A story whose kind is neither addition nor change
    contributes to neither. When no stored story row in the sprint carries a
    kind at all, the answer is None (no data, not zero; no backfill).
    """
    has_any_kind = any(kinds.get(card_id) is not None for card_id in events_by_card)
    if not has_any_kind:
        return None
    addition = 0
    change = 0
    for card_id, events in events_by_card.items():
        kind = kinds.get(card_id)
        if kind is None:
            continue
        minutes = _card_total_minutes(events)
        if kind == "addition":
            addition += minutes
        elif kind == "change":
            change += minutes
    return {"addition": addition, "change": change}


def cost_by_kind_total(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]],
    kinds: Mapping[str, str | None],
    kind: str,
) -> int | None:
    """The sprint's working-time total for stories of the given kind, in whole minutes.

    Returns None when no stored story row in the sprint carries a kind at all
    (no data, not zero). The ``kind`` argument is the story kind string
    (for example 'addition' or 'change').
    """
    answer = calculate_cost_by_kind(events_by_card, kinds)
    if answer is None:
        return None
    return answer.get(kind, 0)


def calculate_model_time_split(
    splits: Mapping[str, tuple[int | None, int | None]],
) -> dict | None:
    """The sprint's model time split into refinement and delivery, in whole minutes.

    ``splits`` maps each card_id to the (refinement, delivery) model seconds
    its finished event's cost payload carried. Each story's two values are
    converted to whole minutes (rounded, the model_minutes display unit) and
    the sprint's split is the sum across the stories that carry a split, so a
    story with a smaller refinement share pulls the sprint's refinement total
    down against its delivery total. ``None`` when no story in the sprint
    carries a split (the pre-Goal payloads, or no costed stories at all), so a
    sprint without split data reads as no data, not zero.
    """
    if not splits:
        return None
    refinement = 0
    delivery = 0
    for refinement_seconds, delivery_seconds in splits.values():
        if refinement_seconds is not None:
            refinement += round(refinement_seconds / 60)
        if delivery_seconds is not None:
            delivery += round(delivery_seconds / 60)
    return {"refinement": refinement, "delivery": delivery}


def model_time_split_total(
    splits: Mapping[str, tuple[int | None, int | None]],
    part: str,
) -> int | None:
    """The sprint's model-time split total for the given part, in whole minutes.

    Returns None when no story in the sprint carries a split (no data, not
    zero). The ``part`` argument is 'refinement' or 'delivery'.
    """
    answer = calculate_model_time_split(splits)
    if answer is None:
        return None
    return answer.get(part, 0)
