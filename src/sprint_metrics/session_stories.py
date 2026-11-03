"""The per-story session-time answer and the sprint's planning part.

The answer reports, for each story whose sessions ran in a sprint: its session
minutes in total and by role (roles named with the crew's role strings), its
model minutes in whole model minutes, and its tokens as whole counts of input
and output tokens. A story's numbers appear whether or not the story
finished. A story with no session record reads null (unknown), never zero.
A story with session records but no delivery sessions (no 'started' board
event, or sessions all before the story's start) reads a true zero: sessions
ran, all of them are planning.
A session counts in the sprint label it was sent with, unclamped to the
sprint's registered span.

The sprint's planning part (session_planning) reports the sessions that ran
before their story's start, with their session minutes and model minutes,
as a named part of the sprint's numbers against the delivery. A story with
session records but no 'started' board event has no established start, and
its sessions read as planning until one is stored. A card-less session is
never planning-or-delivery-of-a-story: it counts in the sprint's numbers
only. A sprint with no carded session records reads session_planning null.
"""

from __future__ import annotations


def calculate_session_stories(
    story_data: dict[str, dict],
) -> dict[str, dict | None]:
    """Compute the per-story session-time answer for a sprint.

    ``story_data`` maps each card to a dict with:
    - ``started_at``: the card's first 'started' event time (datetime or None)
    - ``sessions``: list of (session_start, session_end, role, model_seconds,
      input_tokens, output_tokens)

    Returns a dict mapping card_id to either:
    - A dict with session_minutes, minutes_by_role, model_minutes,
      input_tokens, output_tokens — when the card has delivery sessions
      (sessions that start at or after the story's 'started' event time).
    - A zero dict (session_minutes 0, empty minutes_by_role, model_minutes 0,
      input_tokens 0, output_tokens 0) — when the card has session records
      but no delivery sessions: no 'started' event (so all sessions are
      planning), or sessions that all start before the story's start.
    - None — when the card has no session records at all.

    A story with no session record reads null (unknown), never zero.
    A story with session records but no delivery sessions reads a true zero:
    sessions ran, all of them are planning.
    A session counts in the sprint label it was sent with (no clamping to
    the sprint's registered span).
    """
    result: dict[str, dict | None] = {}

    for card_id, data in story_data.items():
        started_at = data["started_at"]
        sessions = data["sessions"]

        if not sessions:
            result[card_id] = None
            continue

        # Filter to delivery sessions: those that start at or after the
        # story's 'started' event. Without a 'started' event, no session
        # is delivery (all are planning until one is stored).
        if started_at is None:
            result[card_id] = {
                "session_minutes": 0,
                "minutes_by_role": {},
                "model_minutes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            continue

        delivery = [
            (s_start, s_end, role, model_sec, in_tok, out_tok)
            for s_start, s_end, role, model_sec, in_tok, out_tok in sessions
            if s_start >= started_at
        ]

        if not delivery:
            result[card_id] = {
                "session_minutes": 0,
                "minutes_by_role": {},
                "model_minutes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            continue

        # Session minutes in total: sum of (end - start) in whole minutes.
        total_seconds = 0
        role_seconds: dict[str, int] = {}
        total_model_seconds = 0
        total_input_tokens = 0
        total_output_tokens = 0

        for s_start, s_end, role, model_sec, in_tok, out_tok in delivery:
            dur_seconds = int((s_end - s_start).total_seconds())
            total_seconds += dur_seconds
            role_seconds[role] = role_seconds.get(role, 0) + dur_seconds

            if model_sec is not None:
                total_model_seconds += model_sec
            if in_tok is not None:
                total_input_tokens += in_tok
            if out_tok is not None:
                total_output_tokens += out_tok

        session_minutes = round(total_seconds / 60)
        minutes_by_role = {role: round(sec / 60) for role, sec in role_seconds.items()}
        model_minutes = round(total_model_seconds / 60)

        result[card_id] = {
            "session_minutes": session_minutes,
            "minutes_by_role": minutes_by_role,
            "model_minutes": model_minutes,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        }

    return result


def calculate_session_planning(story_data: dict[str, dict]) -> dict | None:
    """Compute the sprint's planning part: the sessions that ran before their
    story's start.

    ``story_data`` has the same shape as for ``calculate_session_stories``.
    Returns ``{"session_minutes": X, "model_minutes": Y}`` where X is the
    total minutes of all planning sessions (sessions that start before the
    story's 'started' event, or all sessions for a story with no 'started'
    event) and Y is the total model minutes of those planning sessions.
    Returns None when the sprint has no carded session records at all.
    """
    if not story_data:
        return None

    # If no card has any session records at all, there is no planning data.
    has_sessions = any(data["sessions"] for data in story_data.values())
    if not has_sessions:
        return None

    total_planning_seconds = 0
    total_planning_model_seconds = 0

    for _card_id, data in story_data.items():
        started_at = data["started_at"]
        sessions = data["sessions"]
        if not sessions:
            continue

        if started_at is None:
            # No established start: all sessions are planning.
            for s_start, s_end, _role, model_sec, _in_tok, _out_tok in sessions:
                total_planning_seconds += int((s_end - s_start).total_seconds())
                if model_sec is not None:
                    total_planning_model_seconds += model_sec
        else:
            # Sessions that start before the story's start are planning.
            for s_start, s_end, _role, model_sec, _in_tok, _out_tok in sessions:
                if s_start < started_at:
                    total_planning_seconds += int((s_end - s_start).total_seconds())
                    if model_sec is not None:
                        total_planning_model_seconds += model_sec

    return {
        "session_minutes": round(total_planning_seconds / 60),
        "model_minutes": round(total_planning_model_seconds / 60),
    }


def _attach_range_session_stories(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the per-story session-time answer and the sprint's planning part
    to each range entry.

    The answer is computed from the sprint's session records and board
    events, independent of the delivery-event gate: a sprint whose only
    stored sessions are for stories that never finished still answers its
    per-story session numbers. An entry for a sprint with no session
    records and no started stories carries session_stories with null
    values for every story and session_planning null. A story with no
    session record reads null (unknown), never zero. A story with session
    records but no delivery sessions reads a true zero.
    """
    from sprint_metrics.store import query_session_story_data

    for label in labels:
        story_data = query_session_story_data(conn, label)
        result["sprints"][label]["session_stories"] = calculate_session_stories(
            story_data
        )
        result["sprints"][label]["session_planning"] = calculate_session_planning(
            story_data
        )


_RANGE_SESSION_STORIES_DESCRIPTION = (
    "Each entry also carries session_stories: the sprint's per-story "
    "session-time answer — for each story whose sessions ran in the sprint, "
    "its session minutes in total (session_minutes, whole minutes), its "
    "minutes by role (minutes_by_role, roles named with the crew's role "
    "strings), its model minutes (model_minutes, whole model minutes), and "
    "its tokens (input_tokens and output_tokens, whole counts). "
    "A story's numbers appear whether or not the story finished. "
    "A story with no session record reads null (unknown), never zero. "
    "A story with session records but no delivery sessions (no 'started' "
    "board event, or sessions all before the story's start) reads a true "
    "zero: sessions ran, all of them are planning. "
    "A session counts in the sprint label it was sent with, unclamped to "
    "the sprint's registered span. "
    "Each entry also carries session_planning: the sprint's planning part — "
    "the sessions that ran before their story's start, with their session "
    "minutes (session_minutes, whole minutes) and model minutes "
    "(model_minutes, whole model minutes), as a named part of the sprint's "
    "numbers against the delivery (the stories' sessions from their starts on). "
    "A story with session records but no 'started' board event has no "
    "established start, and its sessions read as planning until one is "
    "stored. A card-less session is never planning-or-delivery-of-a-story: "
    "it counts in the sprint's numbers only. "
    "A sprint with no carded session records reads session_planning null. "
)
