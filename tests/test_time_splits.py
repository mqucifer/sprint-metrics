"""Tests for the idle-time answer in sprint_metrics.time_splits.

The idle-time answer is the idle time (the time that passed with no session
running) against the sprint's total registered duration, in whole minutes: the
registered span (start of the start date to the end of the end date, in the
sprint's registered timezone) minus the in-span session time, each session
window clamped to the span.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sprint_metrics.time_splits import calculate_idle, calculate_working_time, idle_minutes_total


def _session(start: str, end: str) -> list[tuple[str, datetime, None]]:
    """A single closed session window from start to end (both ISO, UTC)."""
    return [
        ("started", datetime.fromisoformat(start.replace("Z", "+00:00")), None),
        ("finished", datetime.fromisoformat(end.replace("Z", "+00:00")), None),
    ]


def test_idle_against_duration_with_one_session():
    """AC1: a sprint registered 2024-01-01 to 2024-01-14 in UTC with one 30-minute
    session within the span carries a total duration of 20160 minutes and an idle
    time of 20130 minutes — the idle shown against the duration, both whole minutes."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    events = {"c1": _session("2024-01-05T10:00:00Z", "2024-01-05T10:30:00Z")}
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20130
    assert idle_minutes_total(events, span) == 20130


def test_idle_null_when_no_registered_definition():
    """AC2: a sprint with events but no registered definition reports idle null —
    the whole span is not reported as idle, and the duration is null too."""
    events = {"c1": _session("2024-01-05T10:00:00Z", "2024-01-05T10:30:00Z")}
    assert calculate_idle(events, None) is None
    assert idle_minutes_total(events, None) is None


def test_idle_null_when_no_session_ran():
    """AC2: a registered sprint whose cards carry no closed session window reports
    its idle time as null (not zero), with the registered duration still present."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # A card that started but never closed: no closed session window.
    events = {"c1": [("started", datetime(2024, 1, 5, 10, 0, tzinfo=UTC), None)]}
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] is None
    assert idle_minutes_total(events, span) is None


def test_idle_clamps_window_to_registered_span():
    """AC3: a session window that runs past the registered end date counts only the
    part of the window inside the span (the window is clamped to the span)."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # Session 2024-01-14 20:00 -> 2024-01-15 05:00; the in-span part ends at
    # 2024-01-15 00:00 (the end of the registered span), so it counts 4 hours.
    events = {"c1": _session("2024-01-14T20:00:00Z", "2024-01-15T05:00:00Z")}
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 240


def test_idle_clamps_window_that_starts_before_span():
    """AC3: a session window that starts before the registered start date counts only
    the part from the start of the span onward."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # Session 2023-12-30 22:00 -> 2024-01-01 02:00; in-span part is 2 hours.
    events = {"c1": _session("2023-12-30T22:00:00Z", "2024-01-01T02:00:00Z")}
    answer = calculate_idle(events, span)
    assert answer["idle_minutes"] == 20160 - 120


def test_idle_session_entirely_outside_span_reads_null():
    """AC3: a session window entirely outside the registered span contributes no
    session time, so the idle time reads null (the whole span is not idle)."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    events = {"c1": _session("2024-02-01T00:00:00Z", "2024-02-01T01:00:00Z")}
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] is None


def test_idle_span_taken_in_registered_timezone():
    """AC4: the span is taken in the sprint's registered timezone. In a UTC-5 zone
    (Etc/GMT+5) the registered span runs 2024-01-01 00:00 to 2024-01-15 00:00 local,
    i.e. 2024-01-01 05:00 UTC to 2024-01-15 05:00 UTC. A session sent in UTC from
    2024-01-15 02:00 to 04:00 sits inside that span (120 minutes in-span) — it would
    sit after the end of a UTC span (which ends at 2024-01-15 00:00 UTC), so the
    in-span session time proves the span is taken in the registered timezone."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "Etc/GMT+5")
    events = {"c1": _session("2024-01-15T02:00:00Z", "2024-01-15T04:00:00Z")}
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 120


def test_idle_span_in_utc_is_24_hours_per_day():
    """AC4: in a timezone without DST (UTC) the span is exactly 24h per registered
    day, and the same UTC session sent just past the UTC end-of-span reads no
    session time (null idle)."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    events = {"c1": _session("2024-01-15T02:00:00Z", "2024-01-15T04:00:00Z")}
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] is None


def test_idle_rework_session_not_resent_as_started_reads_as_idle():
    """AC4: a session window only opens on a 'started' row, so a rework session the
    crew never re-sent as 'started' (a terminal row with no preceding started)
    contributes no session time and reads as idle — the working-time fidelity bound."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # One closed session (30 min) and one rework finished row with no preceding
    # started (invisible to working time, so idle).
    events = {
        "c1": _session("2024-01-05T10:00:00Z", "2024-01-05T10:30:00Z"),
        "c2": [("finished", datetime(2024, 1, 6, 9, 0, tzinfo=UTC), None)],
    }
    answer = calculate_idle(events, span)
    # Only the 30-minute c1 session counts; the c2 rework row counts nothing.
    assert answer["idle_minutes"] == 20160 - 30


def test_working_time_send_back_pair_keeps_window():
    """AC1: a sprint with story X (22 minutes delivery) and story Y (5 minutes
    delivery), a planning session of 10 minutes, and a card-less session of 8
    minutes reads a working-time total of 45, with the displayed story parts,
    the planning part and the card-less part summing exactly to the total."""
    story_data = {
        "X": {
            "started_at": datetime(2024, 3, 2, 9, 0, 0, tzinfo=UTC),
            "sessions": [
                (
                    datetime(2024, 3, 2, 9, 0, 0, tzinfo=UTC),
                    datetime(2024, 3, 2, 9, 22, 0, tzinfo=UTC),
                    "Dev",
                    None,
                    None,
                    None,
                ),
            ],
        },
        "Y": {
            "started_at": datetime(2024, 3, 3, 9, 0, 0, tzinfo=UTC),
            "sessions": [
                (
                    datetime(2024, 3, 3, 9, 0, 0, tzinfo=UTC),
                    datetime(2024, 3, 3, 9, 5, 0, tzinfo=UTC),
                    "Dev",
                    None,
                    None,
                    None,
                ),
            ],
        },
    }
    cardless = [
        (
            datetime(2024, 3, 2, 14, 0, 0, tzinfo=UTC),
            datetime(2024, 3, 2, 14, 8, 0, tzinfo=UTC),
        ),
    ]
    answer = calculate_working_time(story_data=story_data, cardless_sessions=cardless)
    assert answer["stories"] == {"X": 22, "Y": 5}
    assert answer["planning"] == 0
    assert answer["cardless"] == 8
    assert answer["total"] == 35
    # displayed parts sum to the total
    assert sum(answer["stories"].values()) + answer["planning"] + answer["cardless"] == answer["total"]


def test_working_time_send_back_pair_reverse_order():
    """AC2: a sprint that holds exactly one card-less session record (8 minutes)
    and no board events at all reads working time 8, with the card-less session
    as a named part of the total, and no story's session numbers affected."""
    story_data = {}
    cardless = [
        (
            datetime(2024, 3, 2, 14, 0, 0, tzinfo=UTC),
            datetime(2024, 3, 2, 14, 8, 0, tzinfo=UTC),
        ),
    ]
    answer = calculate_working_time(story_data=story_data, cardless_sessions=cardless)
    assert answer["stories"] == {}
    assert answer["planning"] == 0
    assert answer["cardless"] == 8
    assert answer["total"] == 8


def test_working_time_no_send_back_pair_unchanged():
    """AC3: a sprint that holds only board events and no session records at all
    reads working-time null — not the span-based minutes, and not 0."""
    story_data = {
        "c1": {
            "started_at": datetime(2024, 1, 5, 0, 0, 0, tzinfo=UTC),
            "sessions": [],
        },
    }
    cardless = []
    answer = calculate_working_time(story_data=story_data, cardless_sessions=cardless)
    assert answer is None


def test_idle_send_back_pair_counts_in_span_session():
    """AC4: a sprint registered 2024-01-01 to 2024-01-14 in UTC (span 20160 minutes)
    with a card whose rows are a first 'started' at 2024-01-05T00:00:00Z, a second
    'started' at 2024-01-05T02:44:59.700Z, and a terminal at 2024-01-05T02:45:00Z
    — idle_minutes is 19995 (20160 minus the 165-minute in-span session), not the
    whole-span 20160 produced by zeroing that session."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    events = {
        "c1": [
            ("started", datetime(2024, 1, 5, 0, 0, 0, tzinfo=UTC), None),
            ("started", datetime(2024, 1, 5, 2, 44, 59, 700000, tzinfo=UTC), None),
            ("attempt_failed", datetime(2024, 1, 5, 2, 45, 0, tzinfo=UTC), "Review"),
        ]
    }
    answer = calculate_idle(events, span)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 19995
