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
