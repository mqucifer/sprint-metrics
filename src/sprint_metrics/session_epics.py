"""The per-epic session-time answer for a sprint's /range entry.

The answer reports, for each epic whose stories had sessions in the sprint:
its in-sprint session minutes in total and by role (roles named with the
crew's role strings), its model minutes in whole model minutes, and its
tokens as whole counts of input and output tokens, summed over that
sprint's stories of the epic. An epic appears only when one of its stories
had sessions in the sprint; a story with no epic link contributes to no
epic's total; a card-less session belongs to no epic.
"""

from __future__ import annotations


def calculate_session_epics(
    story_results: dict[str, dict | None],
    card_epics: dict[str, str | None],
) -> dict[str, dict]:
    """Compute the per-epic session-time answer for a sprint.

    ``story_results`` maps each card_id to its per-story session result
    (the output of ``calculate_session_stories``): a dict with
    session_minutes, minutes_by_role, model_minutes, input_tokens,
    output_tokens — or None when the card has no session records.

    ``card_epics`` maps each card_id to its epic (or None when the card's
    stored board rows carry no epic link).

    Returns a dict mapping epic name to its in-sprint session totals:
    session_minutes (whole minutes), minutes_by_role (roles named with the
    crew's role strings), model_minutes (whole model minutes), input_tokens
    and output_tokens (whole counts). An epic appears only when one of its
    stories had sessions in the sprint (a non-None per-story result). A story
    whose per-story result is None (no session records) contributes nothing.
    A story whose card_epics entry is None (no epic link) contributes to no
    epic's total.
    """
    epic_totals: dict[str, dict] = {}

    for card_id, story_result in story_results.items():
        if story_result is None:
            continue
        epic = card_epics.get(card_id)
        if epic is None:
            continue
        if epic not in epic_totals:
            epic_totals[epic] = {
                "session_minutes": 0,
                "minutes_by_role": {},
                "model_minutes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
        totals = epic_totals[epic]
        totals["session_minutes"] += story_result["session_minutes"]
        totals["model_minutes"] += story_result["model_minutes"]
        totals["input_tokens"] += story_result["input_tokens"]
        totals["output_tokens"] += story_result["output_tokens"]
        for role, minutes in story_result["minutes_by_role"].items():
            totals["minutes_by_role"][role] = (
                totals["minutes_by_role"].get(role, 0) + minutes
            )

    return epic_totals


def _attach_range_session_epics(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the per-epic session-time answer to each range entry.

    The answer is computed as a rollup of the per-story session totals,
    joined to each card's epic from its stored board-event rows. An epic
    appears only when one of its stories had sessions in the sprint.
    """
    from sprint_metrics.session_stories import calculate_session_stories
    from sprint_metrics.store import query_card_epics, query_session_story_data

    for label in labels:
        story_data = query_session_story_data(conn, label)
        story_results = calculate_session_stories(story_data)
        card_epics = query_card_epics(conn, set(story_data.keys()))
        result["sprints"][label]["session_epics"] = calculate_session_epics(
            story_results, card_epics
        )


_RANGE_SESSION_EPICS_DESCRIPTION = (
    "Each entry also carries session_epics: the sprint's per-epic "
    "session-time answer — for each epic whose stories had sessions in the "
    "sprint, its in-sprint session minutes in total (session_minutes, whole "
    "minutes), its minutes by role (minutes_by_role, roles named with the "
    "crew's role strings), its model minutes (model_minutes, whole model "
    "minutes), and its tokens (input_tokens and output_tokens, whole "
    "counts), summed over that sprint's stories of the epic. "
    "An epic appears only when one of its stories had sessions in the "
    "sprint. A story whose board rows carry no epic link contributes to no "
    "epic's total; its sessions still appear in the per-story answer. "
    "A card-less session belongs to no epic. "
)
