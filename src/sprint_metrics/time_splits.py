"""The sprint's working-time answer: the minutes of the sprint's session records, per story, planning, and card-less.

Working time is read from the session records stored in the sprint's label:
each story's delivery session minutes (from the story's start on), the
planning sessions' minutes (before their story's start), and the card-less
sessions' minutes (no story). The sprint's working-time total is the sum of
those parts, in whole minutes, and the displayed parts sum exactly to the
displayed sprint total. A session belongs to the sprint label it was sent
with, with no clamping to the registered span. A sprint with no session
records reads null (no data, not zero).

The module also owns the idle-time answer (the registered span minus the
sprint's session minutes, from the same session records that feed the
working time, so the two agree) and the cost-by-kind answer, which still
reads the board-event span windows.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sprint_metrics.store import (
    query_card_kinds,
    query_sprint_span,
    query_working_time_events,
)

_TERMINAL = ("finished", "attempt_failed", "returned")
_STEP_BOUNDARY_PAIR_THRESHOLD = 0.5  # seconds


def _is_step_boundary_pair(
    events: list[tuple[str, datetime, str | None]], index: int
) -> bool:
    """True when the 'started' row at index is the same step boundary as its next terminal row.

    A send-back's 'started' lands less than half a second before its
    'attempt_failed' or 'returned' terminal row; that pair is the same step
    boundary, not a new session window.
    """
    _event_type, event_time, _role = events[index]
    for j in range(index + 1, len(events)):
        next_type, next_time, _next_role = events[j]
        if next_type in _TERMINAL:
            return (next_time - event_time).total_seconds() < _STEP_BOUNDARY_PAIR_THRESHOLD
        if next_type == "started":
            return False
    return False


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
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]] | None = None,
    *,
    story_data: dict[str, dict] | None = None,
    cardless_sessions: list[tuple[datetime, datetime]] | None = None,
) -> dict | None:
    """The sprint's working-time answer: session minutes per story, planning, card-less, and the sprint total.

    ``story_data`` maps each card to a dict with ``started_at`` (the card's
    first 'started' event time or None) and ``sessions`` (a list of
    (session_start, session_end, role, model_seconds, input_tokens,
    output_tokens) tuples), the same shape ``calculate_session_stories`` uses.
    ``cardless_sessions`` is a list of (session_start, session_end) tuples for
    sessions sent with the sprint's label but no card.

    The answer carries:
    - ``stories``: a dict mapping each card_id to its delivery session minutes
      (whole minutes). A story with session records but no delivery sessions
      (all planning) reads 0. A story with no session record does not appear.
    - ``planning``: the total planning session minutes (whole minutes), 0 when
      no planning sessions exist.
    - ``cardless``: the total card-less session minutes (whole minutes), 0 when
      no card-less sessions exist.
    - ``total``: the sum of all stories' delivery minutes, planning, and
      card-less, in whole minutes.

    Returns ``None`` when the sprint holds no session records at all (neither
    carded nor card-less) — no data, not zero. A session belongs to the sprint
    label it was sent with, with no clamping to the registered span.

    ``events_by_card`` is accepted for backward compatibility but no longer
    feeds the working-time answer (the span-window calculation was replaced by
    the session-record computation).
    """
    from sprint_metrics.session_stories import calculate_session_planning, calculate_session_stories

    if story_data is None:
        story_data = {}
    if cardless_sessions is None:
        cardless_sessions = []

    has_carded = any(data["sessions"] for data in story_data.values())
    has_cardless = len(cardless_sessions) > 0
    if not has_carded and not has_cardless:
        return None

    stories: dict[str, int] = {}
    for card_id, data in story_data.items():
        if not data["sessions"]:
            continue
        result = calculate_session_stories({card_id: data})[card_id]
        if result is not None:
            stories[card_id] = result["session_minutes"]

    planning_answer = calculate_session_planning(story_data)
    planning = planning_answer["session_minutes"] if planning_answer is not None else 0

    cardless = 0
    if cardless_sessions:
        cardless = round(
            sum((end - start).total_seconds() for start, end in cardless_sessions) / 60
        )

    total = sum(stories.values()) + planning + cardless
    return {
        "stories": stories,
        "planning": planning,
        "cardless": cardless,
        "total": total,
    }


def working_time_total(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]] | None = None,
    *,
    story_data: dict[str, dict] | None = None,
    cardless_sessions: list[tuple[datetime, datetime]] | None = None,
) -> int | None:
    """The sprint's working-time total in whole minutes, or None when no session records are held.

    The same total the /range working-time answer carries, answered on its own
    for /trend and the prior/delta figures.

    ``events_by_card`` is accepted for backward compatibility but no longer
    feeds the working-time total (the span-window calculation was replaced by
    the session-record computation).
    """
    answer = calculate_working_time(story_data=story_data, cardless_sessions=cardless_sessions)
    return answer["total"] if answer is not None else None


def _sprint_span_datetimes(
    start_date: date, end_date: date, timezone: str
) -> tuple[datetime, datetime]:
    """The sprint's registered span as (start, end) datetimes in the registered timezone.

    The span runs from the start of the registered start date to the end of the
    registered end date (the day after it, at midnight), in the sprint's
    registered timezone, so a day that is not twenty-four hours (a DST
    transition) reads as the minutes that actually elapsed.
    """
    tz = ZoneInfo(timezone)
    span_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=tz)
    end = end_date + timedelta(days=1)
    span_end = datetime(end.year, end.month, end.day, tzinfo=tz)
    return span_start, span_end


def calculate_idle(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]] | None = None,
    span: tuple[date, date, str] | None = None,
    *,
    story_data: dict[str, dict] | None = None,
    cardless_sessions: list[tuple[datetime, datetime]] | None = None,
) -> dict | None:
    """The sprint's idle-time answer: the registered span minus the sprint's session minutes, in whole minutes.

    ``span`` is the sprint's registered definition (start_date, end_date,
    timezone), or None when the sprint has no registered definition.
    ``story_data`` maps each card to a dict with ``started_at`` and
    ``sessions``, and ``cardless_sessions`` is a list of
    (session_start, session_end) tuples — the sprint's session records, the
    same shape the working-time answer uses. The idle time is the registered
    span minus the same session minutes the working time uses (the
    working-time total: the stories' session minutes from each story's start
    on, the planning sessions' minutes, and the card-less sessions'
    minutes), so the working time and the idle time agree from the same
    session records.

    The span runs from the start of the registered start date to the end of
    the registered end date, in the sprint's registered timezone; the total
    duration is that span in whole minutes. A session belongs to the sprint
    label it was sent with, with no clamping to the registered span: when the
    sprint's session minutes exceed its registered span the idle time is
    negative, and when they exactly fill the span it is zero.

    The answer is null (no data, not zero) where the sprint has no registered
    definition or holds no session records — the whole span is not reported
    as idle.

    ``events_by_card`` is accepted for backward compatibility but no longer
    feeds the idle-time answer (the span-window calculation was replaced by
    the session-record computation).
    """
    if span is None:
        return None
    session_minutes = working_time_total(
        story_data=story_data, cardless_sessions=cardless_sessions
    )
    if session_minutes is None:
        return None
    start_date, end_date, timezone = span
    span_start, span_end = _sprint_span_datetimes(start_date, end_date, timezone)
    sprint_duration_minutes = round((span_end - span_start).total_seconds() / 60)
    return {
        "sprint_duration_minutes": sprint_duration_minutes,
        "idle_minutes": sprint_duration_minutes - session_minutes,
    }


def idle_minutes_total(
    events_by_card: Mapping[str, list[tuple[str, datetime, str | None]]] | None = None,
    span: tuple[date, date, str] | None = None,
    *,
    story_data: dict[str, dict] | None = None,
    cardless_sessions: list[tuple[datetime, datetime]] | None = None,
) -> int | None:
    """The sprint's idle time in whole minutes, or None when the sprint has no registered definition or no session records.

    The same idle minutes the /range idle answer carries, answered on its own
    for /trend and the prior/delta figures: the registered span minus the
    sprint's session minutes, from the same session records that feed the
    working time.

    ``events_by_card`` is accepted for backward compatibility but no longer
    feeds the idle-time total (the span-window calculation was replaced by
    the session-record computation).
    """
    answer = calculate_idle(
        span=span, story_data=story_data, cardless_sessions=cardless_sessions
    )
    return answer["idle_minutes"] if answer is not None else None


def _card_total_minutes(
    events: list[tuple[str, datetime, str | None]],
) -> int:
    """Total working time in whole minutes for a single card's ordered event rows."""
    total = 0
    open_window: datetime | None = None
    blocked: list[datetime] = []
    unblocked: list[datetime] = []
    for i, (event_type, event_time, _role) in enumerate(events):
        if event_type == "started":
            if open_window is not None and _is_step_boundary_pair(events, i):
                continue
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


def calculate_model_time_split(splits: dict[str, dict]) -> dict | None:
    """The sprint's model time split into planning and delivery, in whole minutes.

    ``splits`` has the same shape as for ``calculate_session_stories``:
    a dict mapping each card to a dict with ``started_at`` and ``sessions``.
    The planning part is the model seconds of sessions that start before the
    story's 'started' event (or all sessions for a story with no 'started'
    event); the delivery part is the model seconds of sessions that start at
    or after the story's 'started' event. Each part is converted to whole
    minutes (rounded). Returns ``None`` when no story in the sprint carries
    session records (no data, not zero).
    """
    if not splits:
        return None
    has_sessions = any(data["sessions"] for data in splits.values())
    if not has_sessions:
        return None
    planning_seconds = 0
    delivery_seconds = 0
    for _card_id, data in splits.items():
        started_at = data["started_at"]
        sessions = data["sessions"]
        if not sessions:
            continue
        if started_at is None:
            for _s_start, _s_end, _role, model_sec, _in_tok, _out_tok in sessions:
                if model_sec is not None:
                    planning_seconds += model_sec
        else:
            for s_start, _s_end, _role, model_sec, _in_tok, _out_tok in sessions:
                if model_sec is not None:
                    if s_start < started_at:
                        planning_seconds += model_sec
                    else:
                        delivery_seconds += model_sec
    return {
        "planning": round(planning_seconds / 60),
        "delivery": round(delivery_seconds / 60),
    }


def model_time_split_total(
    splits: dict[str, dict],
    part: str,
) -> int | None:
    """The sprint's model-time split total for the given part, in whole minutes.

    Returns None when no story in the sprint carries session records (no
    data, not zero). The ``part`` argument is 'planning' or 'delivery'.
    """
    answer = calculate_model_time_split(splits)
    if answer is None:
        return None
    return answer.get(part, 0)


def calculate_sprint_model_time(
    story_data: dict[str, dict],
    cardless_sessions: list[tuple],
) -> dict | None:
    """The sprint's total model time across all session records, in whole minutes
    and whole token counts.

    The total includes the stories' delivery sessions, the planning sessions,
    and the card-less sessions. ``story_data`` has the same shape as for
    ``calculate_session_stories``. ``cardless_sessions`` is a list of
    (session_start, session_end, role, model_seconds, input_tokens,
    output_tokens) for the sprint's card-less sessions.

    Returns ``{"model_minutes": X, "input_tokens": Y, "output_tokens": Z}``
    where X, Y, Z are the totals across all sessions. Returns None when the
    sprint has no session records at all (no data, not zero).
    """
    # Check if there are any sessions at all.
    has_card_sessions = any(data["sessions"] for data in story_data.values())
    has_cardless = len(cardless_sessions) > 0
    if not has_card_sessions and not has_cardless:
        return None

    total_model_seconds = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for _card_id, data in story_data.items():
        sessions = data["sessions"]
        if not sessions:
            continue
        for _s_start, _s_end, _role, model_sec, in_tok, out_tok in sessions:
            if model_sec is not None:
                total_model_seconds += model_sec
            if in_tok is not None:
                total_input_tokens += in_tok
            if out_tok is not None:
                total_output_tokens += out_tok

    for entry in cardless_sessions:
        # cardless_sessions entries are (session_start, session_end, role, model_seconds, input_tokens, output_tokens)
        if len(entry) >= 6:
            _s_start, _s_end, _role, model_sec, in_tok, out_tok = entry[0], entry[1], entry[2], entry[3], entry[4], entry[5]
            if model_sec is not None:
                total_model_seconds += model_sec
            if in_tok is not None:
                total_input_tokens += in_tok
            if out_tok is not None:
                total_output_tokens += out_tok

    return {
        "model_minutes": round(total_model_seconds / 60),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }


def _attach_range_working_time(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the working-time answer to each range entry, and its flat name to prior/delta.

    A sprint with no session records carries working_time null (no data, not
    zero). A sprint with session records carries the answer — the stories'
    delivery session minutes, the planning sessions' minutes, and the card-less
    sessions' minutes, in whole minutes, with the displayed parts summing to
    the sprint's total. For every sprint after the first, the flat
    working_time_minutes name appears in that entry's prior and delta whenever
    those objects are present, null where the corresponding sprint has no
    working-time data.
    """
    from sprint_metrics.store import query_cardless_sessions, query_session_story_data

    answers: dict[str, dict | None] = {}
    totals: dict[str, int | None] = {}
    for label in labels:
        story_data = query_session_story_data(conn, label)
        cardless = query_cardless_sessions(conn, label)
        answer = calculate_working_time(story_data=story_data, cardless_sessions=cardless)
        answers[label] = answer
        totals[label] = answer["total"] if answer is not None else None
    for index, label in enumerate(labels):
        entry = result["sprints"][label]
        entry["working_time"] = answers[label]
        if index == 0:
            continue
        prior_label = labels[index - 1]
        current_total = totals[label]
        prior_total = totals[prior_label]
        if isinstance(entry.get("prior"), dict):
            entry["prior"]["working_time_minutes"] = prior_total
        if isinstance(entry.get("delta"), dict):
            entry["delta"]["working_time_minutes"] = (
                current_total - prior_total
                if current_total is not None and prior_total is not None
                else None
            )


def _attach_range_cost_by_kind(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the cost-by-kind answer to each range entry, and its flat names to prior/delta.

    A sprint with no events carries cost_by_kind null. A sprint with events but
    whose stored story rows carry no kind also carries cost_by_kind null (no
    data, not zero; no backfill). For every sprint after the first, the flat
    names addition_working_time_minutes and change_working_time_minutes appear
    in that entry's prior and delta whenever those objects are present, null
    where the corresponding sprint has no kind data.
    """
    answers: dict[str, dict | None] = {}
    flat: dict[str, dict[str, int | None]] = {}
    for label in labels:
        if label in has_events:
            events = query_working_time_events(conn, label)
            kinds = query_card_kinds(conn, label)
            answer = calculate_cost_by_kind(events, kinds)
            answers[label] = answer
            if answer is not None:
                flat[label] = {
                    "addition_working_time_minutes": answer["addition"],
                    "change_working_time_minutes": answer["change"],
                }
            else:
                flat[label] = {
                    "addition_working_time_minutes": None,
                    "change_working_time_minutes": None,
                }
        else:
            answers[label] = None
            flat[label] = {
                "addition_working_time_minutes": None,
                "change_working_time_minutes": None,
            }
    for index, label in enumerate(labels):
        entry = result["sprints"][label]
        entry["cost_by_kind"] = answers[label]
        if index == 0:
            continue
        prior_label = labels[index - 1]
        if isinstance(entry.get("prior"), dict):
            for name in ("addition_working_time_minutes", "change_working_time_minutes"):
                entry["prior"][name] = flat[prior_label][name]
        if isinstance(entry.get("delta"), dict):
            for name in ("addition_working_time_minutes", "change_working_time_minutes"):
                cur, pri = flat[label][name], flat[prior_label][name]
                entry["delta"][name] = cur - pri if cur is not None and pri is not None else None


def _attach_range_model_time_split(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the model-time split answer to each range entry, and its flat names to prior/delta.

    The split is computed from the sprint's session records: the planning
    part is the model minutes of sessions that ran before their story's start;
    the delivery part is the model minutes of sessions from the story's start
    on. A sprint with no session records carries model_time_split null (no
    data, not zero). For every sprint after the first, the flat names
    model_time_split_refinement_minutes (the planning part) and
    model_time_split_delivery_minutes appear in that entry's prior and delta
    whenever those objects are present, null where the corresponding sprint
    has no split data.
    """
    from sprint_metrics.store import query_session_story_data

    answers: dict[str, dict | None] = {}
    flat: dict[str, dict[str, int | None]] = {}
    for label in labels:
        if label in has_events:
            story_data = query_session_story_data(conn, label)
            answer = calculate_model_time_split(story_data)
            answers[label] = answer
            if answer is not None:
                flat[label] = {
                    "model_time_split_refinement_minutes": answer["planning"],
                    "model_time_split_delivery_minutes": answer["delivery"],
                }
            else:
                flat[label] = {
                    "model_time_split_refinement_minutes": None,
                    "model_time_split_delivery_minutes": None,
                }
        else:
            answers[label] = None
            flat[label] = {
                "model_time_split_refinement_minutes": None,
                "model_time_split_delivery_minutes": None,
            }
    for index, label in enumerate(labels):
        entry = result["sprints"][label]
        entry["model_time_split"] = answers[label]
        if index == 0:
            continue
        prior_label = labels[index - 1]
        if isinstance(entry.get("prior"), dict):
            for name in (
                "model_time_split_refinement_minutes",
                "model_time_split_delivery_minutes",
            ):
                entry["prior"][name] = flat[prior_label][name]
        if isinstance(entry.get("delta"), dict):
            for name in (
                "model_time_split_refinement_minutes",
                "model_time_split_delivery_minutes",
            ):
                cur, pri = flat[label][name], flat[prior_label][name]
                entry["delta"][name] = cur - pri if cur is not None and pri is not None else None


def _attach_range_model_time(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the sprint's model-time total answer to each range entry, and its flat names to prior/delta.

    The sprint's model time is the total model minutes and tokens across all
    session records (stories, planning, and card-less sessions). A sprint with
    no session records carries model_time null (no data, not zero). For every
    sprint after the first, the flat names model_time_minutes,
    model_time_input_tokens, and model_time_output_tokens appear in that
    entry's prior and delta whenever those objects are present, null where
    the corresponding sprint has no model-time data.
    """
    from sprint_metrics.store import query_cardless_session_details, query_session_story_data

    answers: dict[str, dict | None] = {}
    flat: dict[str, dict[str, int | None]] = {}
    for label in labels:
        if label in has_events:
            story_data = query_session_story_data(conn, label)
            cardless = query_cardless_session_details(conn, label)
            answer = calculate_sprint_model_time(story_data, cardless)
            answers[label] = answer
            if answer is not None:
                flat[label] = {
                    "model_time_minutes": answer["model_minutes"],
                    "model_time_input_tokens": answer["input_tokens"],
                    "model_time_output_tokens": answer["output_tokens"],
                }
            else:
                flat[label] = {
                    "model_time_minutes": None,
                    "model_time_input_tokens": None,
                    "model_time_output_tokens": None,
                }
        else:
            answers[label] = None
            flat[label] = {
                "model_time_minutes": None,
                "model_time_input_tokens": None,
                "model_time_output_tokens": None,
            }
    for index, label in enumerate(labels):
        entry = result["sprints"][label]
        entry["model_time"] = answers[label]
        if index == 0:
            continue
        prior_label = labels[index - 1]
        if isinstance(entry.get("prior"), dict):
            for name in (
                "model_time_minutes",
                "model_time_input_tokens",
                "model_time_output_tokens",
            ):
                entry["prior"][name] = flat[prior_label][name]
        if isinstance(entry.get("delta"), dict):
            for name in (
                "model_time_minutes",
                "model_time_input_tokens",
                "model_time_output_tokens",
            ):
                cur, pri = flat[label][name], flat[prior_label][name]
                entry["delta"][name] = cur - pri if cur is not None and pri is not None else None


_RANGE_MODEL_TIME_DESCRIPTION = (
    "Each entry also carries a model_time answer: the sprint's total "
    "model time across all session records (stories, planning, and "
    "card-less sessions), in whole model minutes and whole token "
    "counts. A sprint with no session records reads null (no data, "
    "not zero). "
)


def _attach_range_idle(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the per-sprint idle-time answer to the range response, and its flat name to prior/delta.

    Each sprint's entry carries its idle answer — the registered sprint span
    minus the sprint's session minutes, from the same session records that
    feed the working time, in whole minutes, in the sprint's registered
    timezone. A sprint with no session records, or with no registered
    definition, carries idle null (no data, not zero) — the whole span is not
    reported as idle. For every sprint after the first, the flat
    ``idle_minutes`` name appears in that entry's prior and delta whenever
    those objects are present, null where the corresponding sprint has no
    idle data.
    """
    from sprint_metrics.store import query_cardless_sessions, query_session_story_data

    answers: dict[str, dict | None] = {}
    totals: dict[str, int | None] = {}
    for label in labels:
        story_data = query_session_story_data(conn, label)
        cardless = query_cardless_sessions(conn, label)
        answer = calculate_idle(
            span=query_sprint_span(conn, label),
            story_data=story_data,
            cardless_sessions=cardless,
        )
        answers[label] = answer
        totals[label] = answer["idle_minutes"] if answer is not None else None
    for index, label in enumerate(labels):
        entry = result["sprints"][label]
        entry["idle"] = answers[label]
        if index == 0:
            continue
        prior_label = labels[index - 1]
        current_total = totals[label]
        prior_total = totals[prior_label]
        if isinstance(entry.get("prior"), dict):
            entry["prior"]["idle_minutes"] = prior_total
        if isinstance(entry.get("delta"), dict):
            entry["delta"]["idle_minutes"] = (
                current_total - prior_total
                if current_total is not None and prior_total is not None
                else None
            )


_RANGE_WORKING_TIME_DESCRIPTION = (
    "Each entry also carries a working_time answer: the sprint's "
    "working time — the minutes of the sprint's session records, "
    "in whole minutes. The stories' session minutes (from each "
    "story's start on), the planning sessions' minutes (before "
    "their story's start), and the card-less sessions' minutes "
    "(no story) sum to the sprint's total. A session belongs "
    "to the sprint label it was sent with, with no clamping "
    "to the registered span. A sprint with no session records "
    "reads null (no data, not zero). "
)

_RANGE_COST_BY_KIND_DESCRIPTION = (
    "Each entry also carries a cost_by_kind answer: the sprint's "
    "working time split by story kind (addition and change), in "
    "whole minutes; a sprint whose stored story rows carry no "
    "kind reads null (no data, not zero). "
)

_RANGE_MODEL_TIME_SPLIT_DESCRIPTION = (
    "Each entry also carries a model_time_split answer: the "
    "sprint's model time split into planning and delivery, in "
    "whole model minutes, from the session records. The planning "
    "part is the model minutes of sessions that ran before their "
    "story's start; the delivery part is the model minutes of "
    "sessions from the story's start on. A sprint with no "
    "carded session records reads null (no data, not zero). "
)

_RANGE_IDLE_DESCRIPTION = (
    "Each entry also carries an idle answer: the sprint's idle "
    "time — the registered sprint span minus the sprint's session "
    "minutes, from the same session records that feed the working "
    "time, in whole minutes, in the sprint's registered timezone "
    "(a session belongs to the sprint label it was sent with, with "
    "no clamping to the registered span; the span-window "
    "calculation no longer feeds the idle answer); a sprint with "
    "no session records, or with no registered definition, reads "
    "null (no data, not zero)."
)
