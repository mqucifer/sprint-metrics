"""The per-story session-time answer: each story's session minutes, by role, model minutes, and tokens.

The answer reports, for each story whose sessions ran in a sprint: its session
minutes in total and by role (roles named with the crew's role strings), its
model minutes in whole model minutes, and its tokens as whole counts of input
and output tokens. A story's numbers appear whether or not the story
finished. A story with no session record reads null (unknown), never zero.
A session counts in the sprint label it was sent with, unclamped to the
sprint's registered span.
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
      input_tokens, output_tokens — when the card has at least one
      delivery session (a session that starts at or after the story's
      'started' event time).
    - None — when the card has no delivery sessions: no session records at
      all, no 'started' event (so all sessions are planning), or sessions
      that all start before the story's start.

    A story with no session record reads null (unknown), never zero.
    A session counts in the sprint label it was sent with (no clamping to
    the sprint's registered span).
    """
    result: dict[str, dict | None] = {}

    for card_id, data in story_data.items():
        started_at = data["started_at"]
        sessions = data["sessions"]

        # Filter to delivery sessions: those that start at or after the
        # story's 'started' event. Without a 'started' event, no session
        # is delivery (all are planning until one is stored).
        if started_at is None:
            result[card_id] = None
            continue

        delivery = [
            (s_start, s_end, role, model_sec, in_tok, out_tok)
            for s_start, s_end, role, model_sec, in_tok, out_tok in sessions
            if s_start >= started_at
        ]

        if not delivery:
            result[card_id] = None
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


def _attach_range_session_stories(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the per-story session-time answer to each range entry.

    The answer is computed from the sprint's session records and board
    events, independent of the delivery-event gate: a sprint whose only
    stored sessions are for stories that never finished still answers its
    per-story session numbers. An entry for a sprint with no session
    records and no started stories carries session_stories with null
    values for every story. A story with no session record reads null
    (unknown), never zero.
    """
    from sprint_metrics.store import query_session_story_data

    for label in labels:
        story_data = query_session_story_data(conn, label)
        result["sprints"][label]["session_stories"] = calculate_session_stories(
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
    "A session counts in the sprint label it was sent with, unclamped to "
    "the sprint's registered span. "
)
