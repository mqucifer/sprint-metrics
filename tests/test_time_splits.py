"""Tests for the idle-time answer in sprint_metrics.time_splits.

The idle-time answer is the registered sprint span minus the sprint's session
minutes, from the same session records that feed the working time, in whole
minutes: the working time and the idle time agree from the same session
records (the working time plus the idle time is the sprint's registered
duration). A session belongs to the sprint label it was sent with, with no
clamping to the sprint's registered span.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sprint_metrics.time_splits import (
    calculate_idle,
    calculate_working_time,
    idle_minutes_total,
    working_time_total,
)


def _dt(s: str) -> datetime:
    """Parse an ISO-8601 datetime string to a timezone-aware datetime."""
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _story(started_at: str, session_start: str, session_end: str) -> dict:
    """A story with a single delivery session (from its start on)."""
    return {
        "started_at": _dt(started_at),
        "sessions": [
            (_dt(session_start), _dt(session_end), "Dev", None, None, None),
        ],
    }


def test_idle_against_duration_with_one_session():
    """AC1: a sprint registered 2024-01-01 to 2024-01-14 in UTC (a span of 20160
    minutes) whose session records total 45 session minutes (27 story, 10
    planning, 8 card-less) reads an idle time of 20115 minutes — the registered
    span minus the same session minutes the working time uses — and the working
    time and the idle time agree from the same session records."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    story_data = {
        "c1": {
            "started_at": _dt("2024-01-05T10:00:00Z"),
            "sessions": [
                # 27 minutes of delivery, from the story's start on.
                (
                    _dt("2024-01-05T10:00:00Z"),
                    _dt("2024-01-05T10:27:00Z"),
                    "Dev",
                    None,
                    None,
                    None,
                ),
                # 10 minutes of planning, before the story's start.
                (
                    _dt("2024-01-05T09:50:00Z"),
                    _dt("2024-01-05T10:00:00Z"),
                    "Dev",
                    None,
                    None,
                    None,
                ),
            ],
        },
    }
    cardless = [(_dt("2024-01-06T14:00:00Z"), _dt("2024-01-06T14:08:00Z"))]
    answer = calculate_idle(span=span, story_data=story_data, cardless_sessions=cardless)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20115
    # The working time and the idle time agree from the same session records.
    assert working_time_total(story_data=story_data, cardless_sessions=cardless) == 45
    assert 45 + answer["idle_minutes"] == answer["sprint_duration_minutes"]
    assert (
        idle_minutes_total(span=span, story_data=story_data, cardless_sessions=cardless)
        == 20115
    )


def test_idle_null_when_no_registered_definition():
    """AC3: a sprint with session records but no registered definition reports
    idle null (no registered span to subtract from) while the working-time total
    still reads from the session records."""
    story_data = {
        "c1": _story("2024-01-05T10:00:00Z", "2024-01-05T10:00:00Z", "2024-01-05T10:30:00Z")
    }
    cardless = [(_dt("2024-01-05T14:00:00Z"), _dt("2024-01-05T14:08:00Z"))]
    assert calculate_idle(span=None, story_data=story_data, cardless_sessions=cardless) is None
    assert (
        idle_minutes_total(span=None, story_data=story_data, cardless_sessions=cardless)
        is None
    )
    # The working-time answer still reads from the session records.
    assert working_time_total(story_data=story_data, cardless_sessions=cardless) == 38


def test_idle_null_when_no_session_ran():
    """AC2: a registered sprint that holds only board events and no session
    records reports its idle answer null (no data, not zero, and not the
    span-based idle it read before this release)."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    story_data = {"c1": {"started_at": _dt("2024-01-05T10:00:00Z"), "sessions": []}}
    assert calculate_idle(span=span, story_data=story_data, cardless_sessions=[]) is None
    assert idle_minutes_total(span=span, story_data=story_data, cardless_sessions=[]) is None


def test_idle_clamps_window_to_registered_span():
    """AC1 (contract change): a session window that runs past the registered end date
    counts in full, not clamped to the span (the span-window calculation no longer
    feeds the idle answer): a 9-hour session counts as 540 minutes, not the 4
    hours that sat inside the span."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    story_data = {"c1": _story("2024-01-14T20:00:00Z", "2024-01-14T20:00:00Z", "2024-01-15T05:00:00Z")}
    answer = calculate_idle(span=span, story_data=story_data, cardless_sessions=[])
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 540


def test_idle_clamps_window_that_starts_before_span():
    """AC1 (contract change): a session window that starts before the registered
    start date counts in full, not clamped to the span: a 4-hour session counts
    as 240 minutes, not the 2 hours that sat inside the span."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    story_data = {"c1": _story("2023-12-30T22:00:00Z", "2023-12-30T22:00:00Z", "2024-01-01T02:00:00Z")}
    answer = calculate_idle(span=span, story_data=story_data, cardless_sessions=[])
    assert answer["idle_minutes"] == 20160 - 240


def test_idle_session_entirely_outside_span_reads_null():
    """AC1 (contract change): a session window entirely outside the registered span
    still counts in the sprint's session minutes (no clamping) — but a sprint that
    holds no session records at all reads null: with no session records, the idle
    answer reads null (no data, not zero), the whole span is not reported as
    idle."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # A session entirely outside the span still counts (unclamped):
    cardless = [(_dt("2024-02-01T00:00:00Z"), _dt("2024-02-01T01:00:00Z"))]
    answer = calculate_idle(span=span, story_data={}, cardless_sessions=cardless)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 60
    # But a sprint with no session records at all reads null:
    assert calculate_idle(span=span, story_data={}, cardless_sessions=[]) is None


def test_idle_span_taken_in_registered_timezone():
    """AC1: the span is taken in the sprint's registered timezone: a 14-day sprint
    registered in a UTC-5 zone (Etc/GMT+5) still spans 20160 minutes (no DST in
    January), and the idle time is the span minus the sprint's session minutes."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "Etc/GMT+5")
    cardless = [(_dt("2024-01-05T10:00:00Z"), _dt("2024-01-05T10:30:00Z"))]
    answer = calculate_idle(span=span, story_data={}, cardless_sessions=cardless)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 30


def test_idle_span_in_utc_is_24_hours_per_day():
    """AC1: in a timezone without DST (UTC) the span is exactly 24h per registered
    day, and a session sent just past the UTC end-of-span still counts (no
    clamping), so the idle time is the span minus the session minutes."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    cardless = [(_dt("2024-01-15T02:00:00Z"), _dt("2024-01-15T04:00:00Z"))]
    answer = calculate_idle(span=span, story_data={}, cardless_sessions=cardless)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 120


def test_idle_rework_session_not_resent_as_started_reads_as_idle():
    """AC2: the idle answer reads from the session records only (the span-window
    calculation no longer feeds it): a card with a 30-minute session and a
    rework row the crew never re-sent as 'started' (a terminal row with no
    preceding started, no session record) contributes no session time — the idle
    time is the span minus the 30 minutes, unchanged by the rework row."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    story_data = {
        "c1": _story("2024-01-05T10:00:00Z", "2024-01-05T10:00:00Z", "2024-01-05T10:30:00Z"),
        # c2 carries a rework terminal row with no session record; the idle
        # answer does not read board events, so it contributes no session time.
        "c2": {"started_at": _dt("2024-01-06T09:00:00Z"), "sessions": []},
    }
    answer = calculate_idle(span=span, story_data=story_data, cardless_sessions=[])
    assert answer["idle_minutes"] == 20160 - 30


def test_idle_send_back_pair_counts_in_span_session():
    """AC1 (contract change): a sprint registered 2024-01-01 to 2024-01-14 in UTC
    (span 20160 minutes) with a story whose session runs from
    2024-01-05T00:00:00Z to 2024-01-05T02:45:00Z (165 minutes) reads idle 19995
    (20160 minus the 165-minute session, counted in full, unclamped)."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    story_data = {"c1": _story("2024-01-05T00:00:00Z", "2024-01-05T00:00:00Z", "2024-01-05T02:45:00Z")}
    answer = calculate_idle(span=span, story_data=story_data, cardless_sessions=[])
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 19995


def test_idle_negative_when_session_minutes_exceed_span():
    """Q1: when the sprint's session minutes exceed its registered span the idle
    time is negative — the registered span minus the session minutes, with no
    clamping: a 25000-minute card-less session against a 20160-minute span reads
    -4840."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # 2024-01-01 00:00 -> 2024-01-18 08:40 is 25000 minutes.
    cardless = [(_dt("2024-01-01T00:00:00Z"), _dt("2024-01-18T08:40:00Z"))]
    answer = calculate_idle(span=span, story_data={}, cardless_sessions=cardless)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 20160 - 25000


def test_idle_zero_when_session_minutes_fill_span():
    """Q1: when the sprint's session minutes exactly fill its registered span the
    idle time reads zero."""
    span = (date(2024, 1, 1), date(2024, 1, 14), "UTC")
    # 2024-01-01 00:00 -> 2024-01-15 00:00 is exactly the 20160-minute span.
    cardless = [(_dt("2024-01-01T00:00:00Z"), _dt("2024-01-15T00:00:00Z"))]
    answer = calculate_idle(span=span, story_data={}, cardless_sessions=cardless)
    assert answer["sprint_duration_minutes"] == 20160
    assert answer["idle_minutes"] == 0


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
    assert sum(answer["stories"].values()) + answer["planning"] + answer["cardless"] == answer[
        "total"
    ]


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
