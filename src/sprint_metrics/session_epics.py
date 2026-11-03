"""The per-epic session-time answer for a sprint's /range entry.

The answer reports, for each epic whose stories have board rows in the
sprint: its in-sprint session minutes in total and by role (roles named
with the crew's role strings), its model minutes in whole model minutes,
and its tokens as whole counts of input and output tokens, summed over that
sprint's stories of the epic. An epic whose stories carried no session
record in the sprint reads unknown (None) for its in-sprint total, never
zero; where only some of its stories have records, the entry lists the
unknown stories beside the total. A story with no epic link contributes to
no epic's total; a card-less session belongs to no epic.

The to-date part (session_epics_to_date) reports, for each epic whose
stories have board rows in the current sprint, the same measures
accumulated across every sprint to date, bridging gap sprints (a sprint
with no sessions carries the prior to-date total forward without resetting
to zero). An epic whose stories have no session record in any sprint up to
and including the current one reads unknown (None) for its to-date total,
never zero.
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


def calculate_session_epics_complete(
    story_results: dict[str, dict | None],
    card_epics: dict[str, str | None],
) -> dict[str, dict]:
    """Compute the per-epic session-time answer with unknown semantics.

    An epic whose stories carried no session record in the sprint reads
    unknown (None) for its in-sprint total, never zero. Where only some of
    its stories have records, the in-sprint total covers only the stories
    with session records, and the entry lists the unknown stories beside the
    total (their count and identifiers).

    ``story_results`` maps each card_id to its per-story session result
    (the output of ``calculate_session_stories``): a dict with
    session_minutes, minutes_by_role, model_minutes, input_tokens,
    output_tokens — or None when the card has no session records.

    ``card_epics`` maps each card_id to its epic (or None when the card's
    stored board rows carry no epic link).

    Returns a dict mapping epic name to its in-sprint session totals:
    session_minutes (whole minutes, or None when no story of the epic has a
    session record), minutes_by_role (roles named with the crew's role
    strings, or None), model_minutes (whole model minutes, or None),
    input_tokens and output_tokens (whole counts, or None). An epic appears
    when one of its stories has board rows in the sprint (a card_epics entry
    for one of its stories). A story whose per-story result is None (no
    session records) contributes nothing to the total but is listed in the
    unknown stories. A story whose card_epics entry is None (no epic link)
    contributes to no epic's total.
    """
    # Base totals: the rollup of stories with session records.
    base = calculate_session_epics(story_results, card_epics)

    # Group all stories by epic (from card_epics, skipping None epics).
    epic_stories: dict[str, list[str]] = {}
    for card_id, epic in card_epics.items():
        if epic is None:
            continue
        if epic not in epic_stories:
            epic_stories[epic] = []
        epic_stories[epic].append(card_id)

    result: dict[str, dict] = {}
    for epic, card_ids in epic_stories.items():
        if epic in base:
            # At least one story has session records: the total covers those.
            entry = dict(base[epic])
            unknown = sorted(
                cid for cid in card_ids if story_results.get(cid) is None
            )
            if unknown:
                entry["unknown_story_count"] = len(unknown)
                entry["unknown_stories"] = unknown
            result[epic] = entry
        else:
            # No story of the epic has session records: the total is unknown.
            result[epic] = {
                "session_minutes": None,
                "minutes_by_role": None,
                "model_minutes": None,
                "input_tokens": None,
                "output_tokens": None,
                "unknown_story_count": len(card_ids),
                "unknown_stories": sorted(card_ids),
            }

    return result


def _attach_range_session_epics(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the per-epic session-time answer (in-sprint and to-date) to
    each range entry.

    The in-sprint answer is computed as a rollup of the per-story session
    totals for the sprint, with unknown semantics: an epic whose stories
    carried no session record in the sprint reads unknown (None) for its
    in-sprint total, never zero; where only some of its stories have
    records, the entry lists the unknown stories beside the total. The
    to-date answer is computed as a rollup of the per-story to-date totals
    (sessions across all sprints up to and including the sprint), with the
    same unknown semantics: an epic whose stories have no session record in
    any sprint up to and including the current one reads unknown (None) for
    its to-date total, never zero.
    """
    from sprint_metrics.session_stories import calculate_session_stories
    from sprint_metrics.store import (
        query_card_epics,
        query_session_story_data,
        query_session_story_data_to_date,
    )

    for label in labels:
        # In-sprint answer with unknown semantics.
        story_data = query_session_story_data(conn, label)
        story_results = calculate_session_stories(story_data)
        card_epics = query_card_epics(conn, set(story_data.keys()))
        result["sprints"][label]["session_epics"] = (
            calculate_session_epics_complete(story_results, card_epics)
        )

        # To-date answer: sessions across all sprints up to and including
        # this sprint, with unknown semantics.
        to_date_data = query_session_story_data_to_date(conn, label)
        to_date_results = calculate_session_stories(to_date_data)
        to_date_card_epics = query_card_epics(conn, set(to_date_data.keys()))
        result["sprints"][label]["session_epics_to_date"] = (
            calculate_session_epics_complete(to_date_results, to_date_card_epics)
        )


_RANGE_SESSION_EPICS_DESCRIPTION = (
    "Each entry also carries session_epics: the sprint's per-epic "
    "session-time answer — for each epic whose stories had sessions in the "
    "sprint, its in-sprint session minutes in total (session_minutes, whole "
    "minutes), its minutes by role (minutes_by_role, roles named with the "
    "crew's role strings), its model minutes (model_minutes, whole model "
    "minutes), and its tokens (input_tokens and output_tokens, whole "
    "counts), summed over that sprint's stories of the epic. "
    "An epic whose stories carried no session record in the sprint reads "
    "unknown (null) for its in-sprint total, never zero: session_minutes, "
    "minutes_by_role, model_minutes, input_tokens and output_tokens are all "
    "null, and the entry lists the unknown stories beside the total (their "
    "count in unknown_story_count and their identifiers in unknown_stories). "
    "Where only some of the epic's stories have session records, the "
    "in-sprint total covers only the stories with records, and the entry "
    "lists the unknown stories beside the total. "
    "A story whose board rows carry no epic link contributes to no epic's "
    "total; its sessions still appear in the per-story answer. "
    "A card-less session belongs to no epic. "
    "Each entry also carries session_epics_to_date: the sprint's per-epic "
    "to-date session-time answer — for each epic whose stories had sessions "
    "in any sprint up to and including this one, the same measures "
    "(session_minutes in whole minutes, minutes by role, model_minutes in "
    "whole model minutes, input_tokens and output_tokens as whole counts) "
    "accumulated across every sprint to date, with gap sprints bridged and "
    "not read as zero. "
    "An epic whose stories have no session record in any sprint up to and "
    "including the current one reads unknown (null) for its to-date total, "
    "never zero; the entry lists the unknown stories beside the total. "
    "A gap sprint with no sessions for the epic carries the prior to-date "
    "total forward. "
    "A story whose board rows carry no epic link contributes to no epic's "
    "to-date total; a card-less session belongs to no epic. "
)
