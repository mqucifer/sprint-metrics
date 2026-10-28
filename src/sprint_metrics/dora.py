"""DORA's four measures per sprint: release frequency, lead time, change failure, and mean time to recovery.

Release frequency is the count of distinct epics whose last story completes in
the sprint (how often epics actually ship). Lead time for changes is the mean,
in whole days, of each released story's span from its creation (the card's
created date) to the release moment (its epic's last story's finished event
time). Change failure is the share of the sprint's releases that came back
with rework (a 'returned' event on a story of the epic after the release
moment), shown as a rate alongside its count. Mean time to recovery is the
mean, in whole minutes, of the completed recovery spans (from the 'returned'
event to the epic's next release moment).
"""

from __future__ import annotations

from datetime import datetime

from sprint_metrics.store import query_dora_data, query_dora_rework_data


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


def calculate_change_failure_and_mttr(
    released_epics: list[str] | None,
    sprint_label: str | None,
    epic_finished: dict[str, list[tuple[datetime, str]]] | None,
    epic_returned: dict[str, list[datetime]] | None,
) -> dict:
    """Return the sprint's change-failure count, rate, and mean-time-to-recovery.

    A release is "bad" (came back with rework) when, after its release moment
    (the latest 'finished' event for that epic in the sprint), a story of the
    epic carries a 'returned' event. The change-failure count is the number of
    bad releases in the sprint; the rate is the whole percent of the sprint's
    releases that came back with rework, shown alongside its count. The mean
    time to recovery is the mean, in whole minutes, of the completed recovery
    spans (from the 'returned' event to the epic's next release moment), over
    the bad releases that re-released.

    All three values are None when no epic link is derivable (released_epics
    is None) or when no epic releases in the sprint (released_epics is empty).
    The rate and MTTR are None when no bad release has completed a recovery.
    """
    if released_epics is None or not released_epics:
        return {
            "change_failure_count": None,
            "change_failure_rate_percent": None,
            "mean_time_to_recovery_minutes": None,
        }

    if sprint_label is None or epic_finished is None or epic_returned is None:
        return {
            "change_failure_count": None,
            "change_failure_rate_percent": None,
            "mean_time_to_recovery_minutes": None,
        }

    bad_release_count = 0
    recovery_spans_minutes: list[float] = []
    release_count = 0

    for epic in released_epics:
        # Find the release moment: the latest 'finished' event for this epic in this sprint
        epic_events = [
            event_time
            for event_time, sprint in epic_finished.get(epic, [])
            if sprint == sprint_label
        ]
        if not epic_events:
            continue
        release_count += 1
        release_moment = max(epic_events)

        # Find returned events after the release moment
        returned_times = [t for t in epic_returned.get(epic, []) if t > release_moment]
        if not returned_times:
            continue

        # This is a bad release
        bad_release_count += 1

        # Find the first returned event (the trigger for the bad release)
        first_returned = min(returned_times)

        # Find the next finished event after the first returned event
        next_finished: datetime | None = None
        for event_time, _sprint in epic_finished.get(epic, []):
            if event_time > first_returned:
                next_finished = event_time
                break

        if next_finished is not None:
            span_minutes = (next_finished - first_returned).total_seconds() / 60
            recovery_spans_minutes.append(span_minutes)

    if release_count == 0:
        return {
            "change_failure_count": None,
            "change_failure_rate_percent": None,
            "mean_time_to_recovery_minutes": None,
        }

    count = bad_release_count
    rate = round(count / release_count * 100)

    if recovery_spans_minutes:
        mttr = round(sum(recovery_spans_minutes) / len(recovery_spans_minutes))
    else:
        mttr = None

    return {
        "change_failure_count": count,
        "change_failure_rate_percent": rate,
        "mean_time_to_recovery_minutes": mttr,
    }


def calculate_dora(
    released_epics: list[str] | None,
    story_spans_days: list[float] | None,
    sprint_label: str | None = None,
    epic_finished: dict[str, list[tuple[datetime, str]]] | None = None,
    epic_returned: dict[str, list[datetime]] | None = None,
    cf_released_epics: list[str] | None = None,
) -> dict:
    """Return the sprint's DORA block.

    ``released_epics`` is the list of epics whose last story completes in the
    sprint, or None when no epic link is derivable. ``story_spans_days`` is
    the list of spans (in days) from each released story's creation to its
    epic's release moment, or None when no epic link is derivable.

    When ``sprint_label``, ``epic_finished`` and ``epic_returned`` are all
    provided, the block also carries the change-failure count, rate, and
    mean-time-to-recovery. ``cf_released_epics`` is the list of epics that
    have at least one 'finished' event in the sprint (used for the
    change-failure measure); when omitted, ``released_epics`` is used.
    """
    result = {
        "release_frequency": calculate_release_frequency(released_epics),
        "lead_time_days": calculate_dora_lead_time(story_spans_days),
    }
    if sprint_label is not None and epic_finished is not None and epic_returned is not None:
        cf_epics = cf_released_epics if cf_released_epics is not None else released_epics
        result.update(
            calculate_change_failure_and_mttr(
                cf_epics, sprint_label, epic_finished, epic_returned
            )
        )
    return result


def _attach_range_dora(
    result: dict, conn, labels: list[str], has_events: set[str]
) -> None:
    """Attach the DORA block to each range entry.

    A sprint with no events carries dora null. A sprint with events but no
    epic links carries dora with all values null (no data, not zero). A
    sprint with epic links carries its release frequency, lead time,
    change-failure count and rate, and mean-time-to-recovery.
    """
    dora_data = query_dora_data(conn, labels)
    rework_data = query_dora_rework_data(conn, labels)
    for label in labels:
        if label not in has_events:
            result["sprints"][label]["dora"] = None
            continue
        released = dora_data["released_epics"].get(label)
        spans = dora_data["story_spans_days"].get(label)
        # For change-failure, an epic "releases" in a sprint if it has at
        # least one 'finished' event in that sprint. Compute this from the
        # rework data (all finished events per epic across all sprints).
        cf_released: list[str] | None = None
        if rework_data["epic_finished"]:
            cf_released = [
                epic
                for epic, events in rework_data["epic_finished"].items()
                if any(sprint == label for _t, sprint in events)
            ]
            if not cf_released:
                cf_released = []
        result["sprints"][label]["dora"] = calculate_dora(
            released,
            spans,
            sprint_label=label,
            epic_finished=rework_data["epic_finished"],
            epic_returned=rework_data["epic_returned"],
            cf_released_epics=cf_released,
        )


_RANGE_DORA_DESCRIPTION = (
    "Each entry also carries a dora block: the sprint's release frequency "
    "(how often epics actually ship) and lead time for changes (the mean, "
    "in whole days, of each released story's span from its creation to its "
    "epic's release moment); a sprint whose finished events carry no epic "
    "link reads null for both, not zero. "
)
