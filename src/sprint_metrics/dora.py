"""DORA's first two measures per sprint: release frequency and lead time for changes.

Release frequency is the count of distinct epics whose last story completes in
the sprint (how often epics actually ship). Lead time for changes is the mean,
in whole days, of each released story's span from its creation (the card's
created date) to the release moment (its epic's last story's finished event
time).
"""

from __future__ import annotations


def calculate_release_frequency(released_epics: list[str] | None) -> int | None:
    """Return the count of distinct epics released in the sprint, or None when no release can be derived.

    A whole count: how often epics actually ship. None when the sprint's
    finished events carry no epic link, so pre-Goal history reads as no data,
    not zero.
    """
    if released_epics is None:
        return None
    return len(released_epics)


def calculate_dora_lead_time(story_spans_days: list[float] | None) -> int | None:
    """Return the mean lead time in whole days over released stories, or None when no release can be derived.

    The mean is of each released story's span from its creation to its epic's
    release moment, rounded to the nearest whole day. None when the sprint's
    finished events carry no epic link, so pre-Goal history reads as no data,
    not zero.
    """
    if story_spans_days is None:
        return None
    if not story_spans_days:
        return None
    return round(sum(story_spans_days) / len(story_spans_days))


def calculate_dora(
    released_epics: list[str] | None,
    story_spans_days: list[float] | None,
) -> dict:
    """Return the sprint's DORA block.

    ``released_epics`` is the list of epics whose last story completes in the
    sprint, or None when no epic link is derivable. ``story_spans_days`` is
    the list of spans (in days) from each released story's creation to its
    epic's release moment, or None when no epic link is derivable.
    """
    return {
        "release_frequency": calculate_release_frequency(released_epics),
        "lead_time_days": calculate_dora_lead_time(story_spans_days),
    }
