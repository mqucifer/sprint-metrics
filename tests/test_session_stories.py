"""Tests for the per-story session-time answer: each story's session minutes, by role, model minutes, and tokens."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, date, datetime

import pytest

from sprint_metrics.service import _start_service
from sprint_metrics.session_stories import (
    calculate_session_planning,
    calculate_session_stories,
)
from sprint_metrics.store import init_db, upsert_session, upsert_sprint

SPRINT_METRICS_DB = os.environ.get("SPRINT_METRICS_DB")

requires_db = pytest.mark.skipif(SPRINT_METRICS_DB is None, reason="SPRINT_METRICS_DB not set")


@pytest.fixture(autouse=True)
def _clean_all_tables():
    """Ensure each test runs against a clean board_events, sprints, and sessions table."""
    if SPRINT_METRICS_DB is None:
        return
    import psycopg

    conn = None
    try:
        conn = psycopg.connect(SPRINT_METRICS_DB, connect_timeout=5)
        conn.execute("DELETE FROM sprint_metrics.board_events")
        conn.execute("DELETE FROM sprint_metrics.sprints")
        conn.execute("DELETE FROM sprint_metrics.sessions")
        conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()


def _dt(s: str) -> datetime:
    """Parse an ISO-8601 datetime string to a timezone-aware datetime."""
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Unit tests for calculate_session_stories
# ---------------------------------------------------------------------------


def test_story_with_sessions_after_start_carries_numbers():
    """AC1: a story with a started event and delivery sessions carries its
    session minutes in total, by role, model minutes, and tokens."""
    started_at = _dt("2024-03-02T09:00:00Z")
    story_data = {
        "story_x": {
            "started_at": started_at,
            "sessions": [
                # Developer: 12 minutes (09:30 -> 09:42)
                (
                    _dt("2024-03-02T09:30:00Z"),
                    _dt("2024-03-02T09:42:00Z"),
                    "Developer",
                    720,
                    3000,
                    600,
                ),
                # Code Reviewer: 2 minutes (10:00 -> 10:02)
                (
                    _dt("2024-03-02T10:00:00Z"),
                    _dt("2024-03-02T10:02:00Z"),
                    "Code Reviewer",
                    60,
                    500,
                    200,
                ),
                # QA Engineer: 8 minutes (11:00 -> 11:08)
                (
                    _dt("2024-03-02T11:00:00Z"),
                    _dt("2024-03-02T11:08:00Z"),
                    "QA Engineer",
                    60,
                    500,
                    100,
                ),
            ],
        }
    }
    result = calculate_session_stories(story_data)
    assert result["story_x"] == {
        "session_minutes": 22,
        "minutes_by_role": {"Developer": 12, "Code Reviewer": 2, "QA Engineer": 8},
        "model_minutes": 14,
        "input_tokens": 4000,
        "output_tokens": 900,
    }


def test_story_without_finish_still_carries_numbers():
    """AC1: a story that has a started event and a session but no finished
    event still carries its session numbers."""
    started_at = _dt("2024-03-02T09:00:00Z")
    story_data = {
        "story_y": {
            "started_at": started_at,
            "sessions": [
                # One 5-minute session by a single role
                (
                    _dt("2024-03-03T09:00:00Z"),
                    _dt("2024-03-03T09:05:00Z"),
                    "Developer",
                    60,
                    100,
                    50,
                ),
            ],
        }
    }
    result = calculate_session_stories(story_data)
    assert result["story_y"] == {
        "session_minutes": 5,
        "minutes_by_role": {"Developer": 5},
        "model_minutes": 1,
        "input_tokens": 100,
        "output_tokens": 50,
    }


def test_story_with_no_session_record_reads_null():
    """AC2: a story with started and finished events but no session record
    reads null."""
    started_at = _dt("2024-03-02T09:00:00Z")
    story_data = {
        "story_z": {
            "started_at": started_at,
            "sessions": [],
        }
    }
    result = calculate_session_stories(story_data)
    assert result["story_z"] is None


def test_story_with_sessions_but_no_started_event_reads_zero():
    """AC3 (R3): a story with session records but no started event has no
    established start; its sessions read as planning, and its per-story
    numbers read a true zero (sessions ran; all of them are planning),
    distinct from the null of a story with no session record."""
    story_data = {
        "story_p": {
            "started_at": None,
            "sessions": [
                (
                    _dt("2024-03-02T09:00:00Z"),
                    _dt("2024-03-02T09:30:00Z"),
                    "Developer",
                    1800,
                    5000,
                    1000,
                ),
            ],
        }
    }
    result = calculate_session_stories(story_data)
    assert result["story_p"] == {
        "session_minutes": 0,
        "minutes_by_role": {},
        "model_minutes": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_session_before_started_event_is_planning_not_delivery():
    """AC2 (R3): a session that starts before the story's started event is
    planning; only sessions from the start count as delivery."""
    started_at = _dt("2024-03-02T12:00:00Z")
    story_data = {
        "story_a": {
            "started_at": started_at,
            "sessions": [
                # Planning session: 30 minutes, starts before the story's start
                (
                    _dt("2024-03-02T09:00:00Z"),
                    _dt("2024-03-02T09:30:00Z"),
                    "Business Analyst",
                    1800,
                    5000,
                    1000,
                ),
                # Delivery session: 5 minutes, starts after the story's start
                (
                    _dt("2024-03-02T13:00:00Z"),
                    _dt("2024-03-02T13:05:00Z"),
                    "Developer",
                    300,
                    500,
                    100,
                ),
            ],
        }
    }
    result = calculate_session_stories(story_data)
    assert result["story_a"] == {
        "session_minutes": 5,
        "minutes_by_role": {"Developer": 5},
        "model_minutes": 5,
        "input_tokens": 500,
        "output_tokens": 100,
    }


def test_session_belongs_to_sprint_label_sent():
    """AC3: a session counts in the sprint label it was sent with, unclamped.
    The pure function has no clamping logic: it computes session_end -
    session_start directly, with no reference to a registered span."""
    # Story started in February (before the session, so the session is delivery)
    started_at = _dt("2024-02-15T09:00:00Z")
    story_data = {
        "story_x": {
            "started_at": started_at,
            "sessions": [
                # A session sent with sprint label 2024-03, whose start
                # (2024-02-28) precedes 2024-03's registered start date
                # (2024-03-01) and whose end follows its registered end.
                (
                    _dt("2024-02-28T10:00:00Z"),
                    _dt("2024-03-31T10:00:00Z"),
                    "Developer",
                    3600,
                    10000,
                    5000,
                ),
            ],
        }
    }
    result = calculate_session_stories(story_data)
    # The whole session counts: from 2024-02-28 to 2024-03-31 is 31 days
    # = 44640 minutes. No clamping to the registered span.
    dur_seconds = int(
        (_dt("2024-03-31T10:00:00Z") - _dt("2024-02-28T10:00:00Z")).total_seconds()
    )
    assert result["story_x"]["session_minutes"] == round(dur_seconds / 60)
    assert result["story_x"]["input_tokens"] == 10000
    assert result["story_x"]["output_tokens"] == 5000


def test_pre_session_sprint_all_stories_read_null():
    """AC2: in a pre-session sprint, every story's session numbers read null,
    never zero."""
    story_data = {
        "story_a": {"started_at": _dt("2024-01-02T09:00:00Z"), "sessions": []},
        "story_b": {"started_at": _dt("2024-01-03T09:00:00Z"), "sessions": []},
    }
    result = calculate_session_stories(story_data)
    assert result["story_a"] is None
    assert result["story_b"] is None


def test_sessions_all_before_started_event_read_zero():
    """AC2 (R3): a story whose sessions all start before its 'started' event
    has no delivery sessions; its per-story numbers read a true zero."""
    started_at = _dt("2024-03-02T12:00:00Z")
    story_data = {
        "story_p": {
            "started_at": started_at,
            "sessions": [
                # A 10-minute session that started before the story's start
                (
                    _dt("2024-03-02T09:00:00Z"),
                    _dt("2024-03-02T09:10:00Z"),
                    "Business Analyst",
                    360,
                    2000,
                    500,
                ),
            ],
        }
    }
    result = calculate_session_stories(story_data)
    assert result["story_p"] == {
        "session_minutes": 0,
        "minutes_by_role": {},
        "model_minutes": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_empty_story_data_returns_empty_dict():
    """No stories at all: the answer is an empty dict."""
    result = calculate_session_stories({})
    assert result == {}


# ---------------------------------------------------------------------------
# Unit tests for calculate_session_planning
# ---------------------------------------------------------------------------


def test_planning_no_carded_sessions_returns_none():
    """A sprint with started events but no session records reads planning null
    (no data, not zero)."""
    story_data = {
        "story_a": {
            "started_at": _dt("2024-03-02T09:00:00Z"),
            "sessions": [],
        }
    }
    result = calculate_session_planning(story_data)
    assert result is None


def test_planning_empty_story_data_returns_none():
    """AC2: a sprint with no carded session records reads session_planning
    null."""
    result = calculate_session_planning({})
    assert result is None


def test_planning_story_without_started_event_counts_all_sessions():
    """AC3: a story with session records but no 'started' board event has no
    established start; its sessions read as planning."""
    story_data = {
        "story_r": {
            "started_at": None,
            "sessions": [
                (
                    _dt("2024-03-02T09:00:00Z"),
                    _dt("2024-03-02T09:07:00Z"),
                    "Business Analyst",
                    420,
                    3000,
                    800,
                ),
            ],
        }
    }
    result = calculate_session_planning(story_data)
    assert result == {
        "session_minutes": 7,
        "model_minutes": 7,
    }


def test_planning_session_before_start_counts_as_planning():
    """AC1/AC2: a session that starts before the story's 'started' event is
    planning; its minutes and model minutes count in the sprint's planning
    part."""
    started_at = _dt("2024-03-02T12:00:00Z")
    story_data = {
        "story_a": {
            "started_at": started_at,
            "sessions": [
                # Planning session: 11 minutes, model time 360 seconds
                (
                    _dt("2024-03-02T08:00:00Z"),
                    _dt("2024-03-02T08:11:00Z"),
                    "Business Analyst",
                    360,
                    5000,
                    1000,
                ),
                # Delivery session: 5 minutes, starts after the story's start
                (
                    _dt("2024-03-02T13:00:00Z"),
                    _dt("2024-03-02T13:05:00Z"),
                    "Developer",
                    300,
                    500,
                    100,
                ),
            ],
        }
    }
    result = calculate_session_planning(story_data)
    assert result == {
        "session_minutes": 11,
        "model_minutes": 6,
    }


def test_planning_mixed_stories_sums_planning_only():
    """AC2: planning is the sum of all planning sessions across all stories.
    Story P has a 10-minute planning session (model 360s); story Q has a
    20-minute delivery session. Planning reads 10 session minutes and 6
    model minutes."""
    story_data = {
        "story_p": {
            "started_at": _dt("2024-01-10T09:00:00Z"),
            "sessions": [
                (
                    _dt("2024-01-05T09:00:00Z"),
                    _dt("2024-01-05T09:10:00Z"),
                    "Business Analyst",
                    360,
                    2000,
                    500,
                ),
            ],
        },
        "story_q": {
            "started_at": _dt("2024-01-08T09:00:00Z"),
            "sessions": [
                (
                    _dt("2024-01-09T09:00:00Z"),
                    _dt("2024-01-09T09:20:00Z"),
                    "Developer",
                    1200,
                    4000,
                    1000,
                ),
            ],
        },
    }
    result = calculate_session_planning(story_data)
    assert result == {
        "session_minutes": 10,
        "model_minutes": 6,
    }


def test_planning_all_delivery_reads_zero():
    """AC2: when all carded sessions are delivery (none before their story's
    start), planning reads a true zero (sessions ran; none are planning)."""
    story_data = {
        "story_a": {
            "started_at": _dt("2024-03-02T09:00:00Z"),
            "sessions": [
                (
                    _dt("2024-03-02T10:00:00Z"),
                    _dt("2024-03-02T10:05:00Z"),
                    "Developer",
                    300,
                    500,
                    100,
                ),
            ],
        }
    }
    result = calculate_session_planning(story_data)
    assert result == {
        "session_minutes": 0,
        "model_minutes": 0,
    }


# ---------------------------------------------------------------------------
# DB-backed integration tests (require SPRINT_METRICS_DB)
# ---------------------------------------------------------------------------


def _post_events(url: str, event: dict) -> tuple[int, dict]:
    """POST an event and return (status, parsed_json_body)."""
    data = json.dumps(event).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _get_json(url: str) -> tuple[int, dict]:
    """GET a URL and return (status, parsed_json_body)."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _make_event(
    card_id: str = "c1",
    event_type: str = "started",
    timestamp: str = "2024-01-03T10:00:00Z",
    sprint: str = "2024-01",
    created: str = "2024-01-01",
) -> dict:
    """Build a valid event dict for POST /events."""
    return {
        "api_version": "1",
        "card_id": card_id,
        "type": event_type,
        "timestamp": timestamp,
        "sprint": sprint,
        "card": {"created": created},
    }


@requires_db
def test_range_session_stories_story_with_sessions():
    """AC1: GET /range over 2024-03 carries story X's session minutes in
    total of 22, minutes by role 12/2/8, 14 model minutes, 4000 input and
    900 output tokens; story Y's numbers (5, 5, 1, 100, 50) appear even
    though Y did not finish; story Z reads null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-03'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2024-03'")
    conn.commit()

    upsert_sprint(conn, "2024-03", date(2024, 3, 1), date(2024, 3, 31), "UTC")

    # Story X: started board event
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_x', 'started', %s, '2024-03', '2024-03-01')""",
        (datetime(2024, 3, 2, 9, 0, tzinfo=UTC),),
    )
    # Story Y: started board event (no finished)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_y', 'started', %s, '2024-03', '2024-03-01')""",
        (datetime(2024, 3, 3, 9, 0, tzinfo=UTC),),
    )
    # Story Z: started and finished, no session records
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_z', 'started', %s, '2024-03', '2024-03-01')""",
        (datetime(2024, 3, 4, 9, 0, tzinfo=UTC),),
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_z', 'finished', %s, '2024-03', '2024-03-01')""",
        (datetime(2024, 3, 5, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # Story X's three sessions
    upsert_session(
        conn,
        {
            "card": "story_x",
            "role": "Developer",
            "start": "2024-03-02T09:30:00Z",
            "end": "2024-03-02T09:42:00Z",
            "sprint": "2024-03",
            "model_seconds": 720,
            "tokens": 3600,
            "input_tokens": 3000,
            "output_tokens": 600,
        },
    )
    upsert_session(
        conn,
        {
            "card": "story_x",
            "role": "Code Reviewer",
            "start": "2024-03-02T10:00:00Z",
            "end": "2024-03-02T10:02:00Z",
            "sprint": "2024-03",
            "model_seconds": 60,
            "tokens": 700,
            "input_tokens": 500,
            "output_tokens": 200,
        },
    )
    upsert_session(
        conn,
        {
            "card": "story_x",
            "role": "QA Engineer",
            "start": "2024-03-02T11:00:00Z",
            "end": "2024-03-02T11:08:00Z",
            "sprint": "2024-03",
            "model_seconds": 60,
            "tokens": 600,
            "input_tokens": 500,
            "output_tokens": 100,
        },
    )
    # Story Y's single session
    upsert_session(
        conn,
        {
            "card": "story_y",
            "role": "Developer",
            "start": "2024-03-03T09:00:00Z",
            "end": "2024-03-03T09:05:00Z",
            "sprint": "2024-03",
            "model_seconds": 60,
            "tokens": 150,
            "input_tokens": 100,
            "output_tokens": 50,
        },
    )

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        ss = body["sprints"]["2024-03"]["session_stories"]
        # Story X: 22 minutes total, 14 model minutes, 4000 in, 900 out
        assert ss["story_x"] == {
            "session_minutes": 22,
            "minutes_by_role": {"Developer": 12, "Code Reviewer": 2, "QA Engineer": 8},
            "model_minutes": 14,
            "input_tokens": 4000,
            "output_tokens": 900,
        }
        # Story Y: 5 minutes, 1 model minute, 100 in, 50 out (did not finish)
        assert ss["story_y"] == {
            "session_minutes": 5,
            "minutes_by_role": {"Developer": 5},
            "model_minutes": 1,
            "input_tokens": 100,
            "output_tokens": 50,
        }
        # Story Z: no session records, reads null
        assert ss["story_z"] is None
    finally:
        conn.close()


@requires_db
def test_range_session_stories_pre_session_sprint_reads_null():
    """AC2: in a pre-session sprint, every story's session numbers read null,
    never zero."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-01'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2024-01'")
    conn.commit()

    upsert_sprint(conn, "2024-01", date(2024, 1, 1), date(2024, 1, 14), "UTC")

    # Board events for two stories
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_a', 'started', %s, '2024-01', '2024-01-01')""",
        (datetime(2024, 1, 2, 9, 0, tzinfo=UTC),),
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_b', 'started', %s, '2024-01', '2024-01-01')""",
        (datetime(2024, 1, 3, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        ss = body["sprints"]["2024-01"]["session_stories"]
        # No session records anywhere: every story reads null
        assert ss["story_a"] is None
        assert ss["story_b"] is None
    finally:
        conn.close()


@requires_db
def test_range_session_stories_session_belongs_to_sprint_label():
    """AC3: a session sent with sprint label 2024-03 whose start precedes
    2024-03's registered start counts in full in 2024-03's story numbers;
    2024-02's story numbers are unaffected."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-02', '2024-03')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-02', '2024-03')")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name IN ('2024-02', '2024-03')")
    conn.commit()

    upsert_sprint(conn, "2024-02", date(2024, 2, 1), date(2024, 2, 29), "UTC")
    upsert_sprint(conn, "2024-03", date(2024, 3, 1), date(2024, 3, 31), "UTC")

    # Give story_x a started event in 2024-02 so that sprint has events
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_x', 'started', %s, '2024-02', '2024-02-01')""",
        (datetime(2024, 2, 15, 9, 0, tzinfo=UTC),),
    )
    # Also give story_x a started event in 2024-03
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_x', 'started', %s, '2024-03', '2024-03-01')""",
        (datetime(2024, 3, 1, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # A session for story_x sent with sprint label 2024-03, whose start
    # precedes 2024-03's registered start date (2024-03-01)
    upsert_session(
        conn,
        {
            "card": "story_x",
            "role": "Developer",
            "start": "2024-02-28T10:00:00Z",
            "end": "2024-03-31T10:00:00Z",
            "sprint": "2024-03",
            "model_seconds": 3600,
            "tokens": 15000,
            "input_tokens": 10000,
            "output_tokens": 5000,
        },
    )

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/range?start=2024-02&end=2024-03"
        )
        assert status == 200
        # The whole session counts in 2024-03 (no clamping)
        ss_03 = body["sprints"]["2024-03"]["session_stories"]
        dur_seconds = int(
            (
                datetime(2024, 3, 31, 10, 0, tzinfo=UTC)
                - datetime(2024, 2, 28, 10, 0, tzinfo=UTC)
            ).total_seconds()
        )
        assert ss_03["story_x"]["session_minutes"] == round(dur_seconds / 60)
        assert ss_03["story_x"]["input_tokens"] == 10000
        assert ss_03["story_x"]["output_tokens"] == 5000
        # 2024-02's story numbers are unaffected (no session in 2024-02)
        ss_02 = body["sprints"]["2024-02"]["session_stories"]
        assert ss_02["story_x"] is None
    finally:
        conn.close()


@requires_db
def test_range_session_planning_counts_sessions_before_start():
    """AC2: GET /range over a sprint displays the sprint's planning as a
    named part — planning session minutes and model minutes, against the
    delivery. Story P carries a 10-minute session before P's start; story Q
    carries a 20-minute session after Q's start. Planning reads 10 session
    minutes and 6 model minutes; P's own session minutes read 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-05'")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-05'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2024-05'")
    conn.commit()

    upsert_sprint(conn, "2024-05", date(2024, 5, 1), date(2024, 5, 31), "UTC")

    # Story P: started board event
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_p', 'started', %s, '2024-05', '2024-05-01')""",
        (datetime(2024, 5, 10, 9, 0, tzinfo=UTC),),
    )
    # Story Q: started board event
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_q', 'started', %s, '2024-05', '2024-05-01')""",
        (datetime(2024, 5, 8, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # Story P's 10-minute planning session (before P's start)
    upsert_session(
        conn,
        {
            "card": "story_p",
            "role": "Business Analyst",
            "start": "2024-05-05T09:00:00Z",
            "end": "2024-05-05T09:10:00Z",
            "sprint": "2024-05",
            "model_seconds": 360,
            "tokens": 2500,
            "input_tokens": 2000,
            "output_tokens": 500,
        },
    )
    # Story Q's 20-minute delivery session (after Q's start)
    upsert_session(
        conn,
        {
            "card": "story_q",
            "role": "Developer",
            "start": "2024-05-09T09:00:00Z",
            "end": "2024-05-09T09:20:00Z",
            "sprint": "2024-05",
            "model_seconds": 1200,
            "tokens": 5000,
            "input_tokens": 4000,
            "output_tokens": 1000,
        },
    )

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-05&end=2024-05")
        assert status == 200
        sprint_entry = body["sprints"]["2024-05"]
        # The sprint's planning part: 10 session minutes, 6 model minutes
        assert sprint_entry["session_planning"] == {
            "session_minutes": 10,
            "model_minutes": 6,
        }
        # Story P: sessions ran, all planning, so delivery reads zero
        ss = sprint_entry["session_stories"]
        assert ss["story_p"] == {
            "session_minutes": 0,
            "minutes_by_role": {},
            "model_minutes": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        # Story Q: delivery session counts
        assert ss["story_q"] == {
            "session_minutes": 20,
            "minutes_by_role": {"Developer": 20},
            "model_minutes": 20,
            "input_tokens": 4000,
            "output_tokens": 1000,
        }
    finally:
        conn.close()


@requires_db
def test_range_session_planning_story_without_started_event():
    """AC3: story R has a session record (7 minutes, model time 420 seconds)
    but no stored 'started' board event. Its 7 minutes and 7 model minutes
    read as the sprint's planning; story R's own session minutes read 0
    (a true zero, distinct from null of a story with no session record)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-06'")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-06'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2024-06'")
    conn.commit()

    upsert_sprint(conn, "2024-06", date(2024, 6, 1), date(2024, 6, 30), "UTC")

    # Story S: has a started event (so the sprint has events)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_s', 'started', %s, '2024-06', '2024-06-01')""",
        (datetime(2024, 6, 5, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # Story R: NO started event, but has a session record
    upsert_session(
        conn,
        {
            "card": "story_r",
            "role": "Business Analyst",
            "start": "2024-06-03T09:00:00Z",
            "end": "2024-06-03T09:07:00Z",
            "sprint": "2024-06",
            "model_seconds": 420,
            "tokens": 3800,
            "input_tokens": 3000,
            "output_tokens": 800,
        },
    )
    # Story S: a delivery session
    upsert_session(
        conn,
        {
            "card": "story_s",
            "role": "Developer",
            "start": "2024-06-06T09:00:00Z",
            "end": "2024-06-06T09:10:00Z",
            "sprint": "2024-06",
            "model_seconds": 600,
            "tokens": 2000,
            "input_tokens": 1500,
            "output_tokens": 500,
        },
    )

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        sprint_entry = body["sprints"]["2024-06"]
        # Planning: story R's 7 minutes (no started event) + 7 model minutes
        assert sprint_entry["session_planning"] == {
            "session_minutes": 7,
            "model_minutes": 7,
        }
        ss = sprint_entry["session_stories"]
        # Story R: sessions ran, all planning, reads a true zero
        assert ss["story_r"] == {
            "session_minutes": 0,
            "minutes_by_role": {},
            "model_minutes": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        # Story S: delivery session counts
        assert ss["story_s"] == {
            "session_minutes": 10,
            "minutes_by_role": {"Developer": 10},
            "model_minutes": 10,
            "input_tokens": 1500,
            "output_tokens": 500,
        }
    finally:
        conn.close()


@requires_db
def test_range_session_planning_null_when_no_carded_sessions():
    """AC2: a sprint with no carded session records reads session_planning
    null (no data, not zero)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-07'")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-07'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2024-07'")
    conn.commit()

    upsert_sprint(conn, "2024-07", date(2024, 7, 1), date(2024, 7, 31), "UTC")

    # Board event so the sprint has events
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('story_a', 'started', %s, '2024-07', '2024-07-01')""",
        (datetime(2024, 7, 2, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-07&end=2024-07")
        assert status == 200
        sprint_entry = body["sprints"]["2024-07"]
        # No session records at all: planning reads null
        assert sprint_entry["session_planning"] is None
        # Story A: no session records, reads null
        assert sprint_entry["session_stories"]["story_a"] is None
    finally:
        conn.close()


@requires_db
def test_description_fragment_lives_in_session_stories_module():
    """AC4: the description fragment is defined in the session_stories module
    and composed into the /range endpoint description."""
    from sprint_metrics.service import _RANGE_DESCRIPTION
    from sprint_metrics.session_stories import _RANGE_SESSION_STORIES_DESCRIPTION

    assert "session_stories" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "session_minutes" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "minutes_by_role" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "model_minutes" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "input_tokens" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "output_tokens" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "null" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "session_planning" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert "planning" in _RANGE_SESSION_STORIES_DESCRIPTION
    assert _RANGE_SESSION_STORIES_DESCRIPTION in _RANGE_DESCRIPTION
