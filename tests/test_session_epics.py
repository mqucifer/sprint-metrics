"""Tests for the per-epic session-time answer: each epic's in-sprint session minutes, by role, model minutes, and tokens, summed over its stories."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from sprint_metrics.service import _start_service
from sprint_metrics.session_epics import (
    calculate_session_epics,
    calculate_session_epics_to_date,
)
from sprint_metrics.store import init_db, upsert_session, upsert_sprint

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"
DOCS_DIR = Path(__file__).parent.parent / "docs"

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


def _get_json(url: str) -> tuple[int, dict]:
    """GET a URL and return (status, parsed JSON body)."""
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


# ---------------------------------------------------------------------------
# Unit tests for calculate_session_epics
# ---------------------------------------------------------------------------


def test_epic_total_equals_sum_of_stories():
    """AC1: an epic's in-sprint total equals the sum of its stories' per-story
    session minutes, by-role minutes, model minutes, and tokens."""
    story_results = {
        "s1": {
            "session_minutes": 22,
            "minutes_by_role": {"Developer": 12, "QA Engineer": 10},
            "model_minutes": 14,
            "input_tokens": 4000,
            "output_tokens": 900,
        },
        "s2": {
            "session_minutes": 8,
            "minutes_by_role": {"Developer": 5, "Code Reviewer": 3},
            "model_minutes": 4,
            "input_tokens": 2000,
            "output_tokens": 500,
        },
    }
    card_epics = {"s1": "E", "s2": "E"}
    result = calculate_session_epics(story_results, card_epics)
    assert result == {
        "E": {
            "session_minutes": 30,
            "minutes_by_role": {"Developer": 17, "QA Engineer": 10, "Code Reviewer": 3},
            "model_minutes": 18,
            "input_tokens": 6000,
            "output_tokens": 1400,
        }
    }


def test_epic_not_present_when_no_story_has_sessions():
    """AC2: an epic whose stories had no sessions in the sprint appears nowhere
    in the epic session answer."""
    story_results = {
        "s1": None,
        "s2": None,
    }
    card_epics = {"s1": "E2", "s2": "E2"}
    result = calculate_session_epics(story_results, card_epics)
    assert result == {}


def test_story_without_epic_contributes_to_no_epic():
    """AC3: a story whose board rows carry no epic link contributes to no
    epic's total."""
    story_results = {
        "s1": {
            "session_minutes": 10,
            "minutes_by_role": {"Developer": 10},
            "model_minutes": 5,
            "input_tokens": 1000,
            "output_tokens": 200,
        },
    }
    card_epics = {"s1": None}
    result = calculate_session_epics(story_results, card_epics)
    assert result == {}


def test_story_without_epic_absent_from_card_epics():
    """AC3: a story whose card_id is absent from card_epics (no board-event
    rows) contributes to no epic's total."""
    story_results = {
        "s1": {
            "session_minutes": 10,
            "minutes_by_role": {"Developer": 10},
            "model_minutes": 5,
            "input_tokens": 1000,
            "output_tokens": 200,
        },
    }
    card_epics = {}
    result = calculate_session_epics(story_results, card_epics)
    assert result == {}


def test_multiple_epics_rollup():
    """Two epics each carry the sum of their own stories' totals."""
    story_results = {
        "s1": {
            "session_minutes": 10,
            "minutes_by_role": {"Developer": 10},
            "model_minutes": 5,
            "input_tokens": 1000,
            "output_tokens": 200,
        },
        "s2": {
            "session_minutes": 20,
            "minutes_by_role": {"QA Engineer": 20},
            "model_minutes": 10,
            "input_tokens": 2000,
            "output_tokens": 400,
        },
    }
    card_epics = {"s1": "E1", "s2": "E2"}
    result = calculate_session_epics(story_results, card_epics)
    assert result == {
        "E1": {
            "session_minutes": 10,
            "minutes_by_role": {"Developer": 10},
            "model_minutes": 5,
            "input_tokens": 1000,
            "output_tokens": 200,
        },
        "E2": {
            "session_minutes": 20,
            "minutes_by_role": {"QA Engineer": 20},
            "model_minutes": 10,
            "input_tokens": 2000,
            "output_tokens": 400,
        },
    }


# ---------------------------------------------------------------------------
# Integration tests for the /range endpoint
# ---------------------------------------------------------------------------


@requires_db
def test_range_session_epics_rollup():
    """AC1: GET /range over 2026-13 carries epic E whose in-sprint session
    minutes total equals S1's plus S2's per-story session minutes, whose
    by-role minutes equal the sum of the two stories' by-role minutes, and
    whose model minutes and tokens equal the sums."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2026-13'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-13'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2026-13'")
    conn.commit()

    upsert_sprint(conn, "2026-13", date(2026, 3, 23), date(2026, 4, 5), "UTC")

    # Story S1: started board event with epic E
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s1', 'started', %s, '2026-13', '2026-03-23', 'E')""",
        (datetime(2026, 3, 24, 9, 0, tzinfo=UTC),),
    )
    # Story S2: started board event with epic E
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s2', 'started', %s, '2026-13', '2026-03-23', 'E')""",
        (datetime(2026, 3, 24, 10, 0, tzinfo=UTC),),
    )
    conn.commit()

    # S1's sessions: Developer 12 min (720s model), Code Reviewer 2 min (60s model)
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-03-24T09:30:00Z",
            "end": "2026-03-24T09:42:00Z",
            "sprint": "2026-13",
            "model_seconds": 720,
            "tokens": 3600,
            "input_tokens": 3000,
            "output_tokens": 600,
        },
    )
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Code Reviewer",
            "start": "2026-03-24T10:00:00Z",
            "end": "2026-03-24T10:02:00Z",
            "sprint": "2026-13",
            "model_seconds": 60,
            "tokens": 700,
            "input_tokens": 500,
            "output_tokens": 200,
        },
    )
    # S2's sessions: Developer 5 min (300s model)
    upsert_session(
        conn,
        {
            "card": "s2",
            "role": "Developer",
            "start": "2026-03-24T11:00:00Z",
            "end": "2026-03-24T11:05:00Z",
            "sprint": "2026-13",
            "model_seconds": 300,
            "tokens": 1500,
            "input_tokens": 1000,
            "output_tokens": 500,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-13&end=2026-13")
        assert status == 200
        entry = body["sprints"]["2026-13"]

        # Per-story session answers (for cross-checking)
        ss = entry["session_stories"]
        # S1: 14 minutes total (12+2), 780s model = 13 min, 3500 in, 800 out
        assert ss["s1"] == {
            "session_minutes": 14,
            "minutes_by_role": {"Developer": 12, "Code Reviewer": 2},
            "model_minutes": 13,
            "input_tokens": 3500,
            "output_tokens": 800,
        }
        # S2: 5 minutes, 300s model = 5 min, 1000 in, 500 out
        assert ss["s2"] == {
            "session_minutes": 5,
            "minutes_by_role": {"Developer": 5},
            "model_minutes": 5,
            "input_tokens": 1000,
            "output_tokens": 500,
        }

        # Epic E: sum of S1 + S2
        se = entry["session_epics"]
        assert se == {
            "E": {
                "session_minutes": 19,  # 14 + 5
                "minutes_by_role": {"Developer": 17, "Code Reviewer": 2},  # 12+5, 2
                "model_minutes": 18,  # 13 + 5
                "input_tokens": 4500,  # 3500 + 1000
                "output_tokens": 1300,  # 800 + 500
            }
        }
    finally:
        conn.close()


@requires_db
def test_range_session_epics_epic_without_sessions_absent():
    """AC2: an epic whose stories ran no session in the sprint appears nowhere
    in the epic session answer; a card-less session contributes to no epic."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2026-13'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-13'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2026-13'")
    conn.commit()

    upsert_sprint(conn, "2026-13", date(2026, 3, 23), date(2026, 4, 5), "UTC")

    # Story S3: started board event with epic E2, no sessions
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s3', 'started', %s, '2026-13', '2026-03-23', 'E2')""",
        (datetime(2026, 3, 24, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # A card-less session in the sprint
    upsert_session(
        conn,
        {
            "card": None,
            "role": "Developer",
            "start": "2026-03-25T09:00:00Z",
            "end": "2026-03-25T09:30:00Z",
            "sprint": "2026-13",
            "model_seconds": 600,
            "tokens": 3000,
            "input_tokens": 2500,
            "output_tokens": 500,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-13&end=2026-13")
        assert status == 200
        entry = body["sprints"]["2026-13"]

        # E2 appears nowhere in the epic session answer
        se = entry["session_epics"]
        assert "E2" not in se
        assert se == {}

        # The card-less session doesn't appear in any epic
        assert se == {}
    finally:
        conn.close()


@requires_db
def test_range_session_epics_story_without_epic_excluded():
    """AC3: a story whose board rows carry no epic link does not contribute to
    any epic's total; its sessions still appear in the per-story answer."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2026-13'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-13'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2026-13'")
    conn.commit()

    upsert_sprint(conn, "2026-13", date(2026, 3, 23), date(2026, 4, 5), "UTC")

    # Story S4: started board event with NO epic
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('s4', 'started', %s, '2026-13', '2026-03-23')""",
        (datetime(2026, 3, 24, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # S4's session
    upsert_session(
        conn,
        {
            "card": "s4",
            "role": "Developer",
            "start": "2026-03-24T09:30:00Z",
            "end": "2026-03-24T09:45:00Z",
            "sprint": "2026-13",
            "model_seconds": 900,
            "tokens": 4500,
            "input_tokens": 4000,
            "output_tokens": 500,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-13&end=2026-13")
        assert status == 200
        entry = body["sprints"]["2026-13"]

        # The story's sessions still appear in the per-story answer
        ss = entry["session_stories"]
        assert ss["s4"] == {
            "session_minutes": 15,
            "minutes_by_role": {"Developer": 15},
            "model_minutes": 15,
            "input_tokens": 4000,
            "output_tokens": 500,
        }

        # No epic's total includes S4's sessions
        se = entry["session_epics"]
        assert se == {}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests for the to-date per-epic session-time answer
# ---------------------------------------------------------------------------


def test_to_date_epic_total_equals_sum_of_stories():
    """AC3: an epic's to-date total equals the sum of its stories' to-date
    per-story session minutes, by-role minutes, model minutes, and tokens."""
    story_results = {
        "s1": {
            "session_minutes": 42,
            "minutes_by_role": {"Developer": 25, "QA Engineer": 17},
            "model_minutes": 30,
            "input_tokens": 10000,
            "output_tokens": 2000,
        },
        "s2": {
            "session_minutes": 18,
            "minutes_by_role": {"Developer": 10, "Code Reviewer": 8},
            "model_minutes": 12,
            "input_tokens": 5000,
            "output_tokens": 1000,
        },
    }
    card_epics = {"s1": "E", "s2": "E"}
    result = calculate_session_epics_to_date(story_results, card_epics)
    assert result == {
        "E": {
            "session_minutes": 60,
            "minutes_by_role": {"Developer": 35, "QA Engineer": 17, "Code Reviewer": 8},
            "model_minutes": 42,
            "input_tokens": 15000,
            "output_tokens": 3000,
        }
    }


def test_to_date_epic_not_present_when_no_story_has_sessions():
    """AC3: an epic whose stories had no sessions in any sprint up to date
    appears nowhere in the to-date answer."""
    story_results = {
        "s1": None,
        "s2": None,
    }
    card_epics = {"s1": "E2", "s2": "E2"}
    result = calculate_session_epics_to_date(story_results, card_epics)
    assert result == {}


@requires_db
def test_range_session_epics_to_date_gap_sprint_bridged():
    """AC1: a gap sprint with no sessions for the epic carries the prior
    to-date total forward, not read as zero. E's story ran 60 minutes in
    2026-10 and 90 minutes in 2026-13, with no session in 2026-12.
    The 2026-13 entry carries to-date 150; the 2026-12 entry carries
    to-date 60."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    for sprint in ("2026-10", "2026-12", "2026-13"):
        conn.execute(f"DELETE FROM sprint_metrics.sessions WHERE sprint = '{sprint}'")
        conn.execute(f"DELETE FROM sprint_metrics.board_events WHERE sprint = '{sprint}'")
        conn.execute(f"DELETE FROM sprint_metrics.sprints WHERE name = '{sprint}'")
    conn.commit()

    upsert_sprint(conn, "2026-10", date(2026, 10, 1), date(2026, 10, 14), "UTC")
    upsert_sprint(conn, "2026-12", date(2026, 12, 1), date(2026, 12, 14), "UTC")
    upsert_sprint(conn, "2026-13", date(2026, 12, 15), date(2026, 12, 28), "UTC")

    # Story S1: started in 2026-10 with epic E
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s1', 'started', %s, '2026-10', '2026-10-01', 'E')""",
        (datetime(2026, 10, 1, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # 60-minute session in 2026-10
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-10-01T10:00:00Z",
            "end": "2026-10-01T11:00:00Z",
            "sprint": "2026-10",
            "model_seconds": 3600,
            "tokens": 6000,
            "input_tokens": 5000,
            "output_tokens": 1000,
        },
    )
    # 90-minute session in 2026-13
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-12-16T10:00:00Z",
            "end": "2026-12-16T11:30:00Z",
            "sprint": "2026-13",
            "model_seconds": 5400,
            "tokens": 9000,
            "input_tokens": 8000,
            "output_tokens": 1000,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Query from 2026-12 to 2026-13
        status, body = _get_json(
            f"http://127.0.0.1:{port}/range?start=2026-12&end=2026-13"
        )
        assert status == 200

        # 2026-12 entry: E appears (had sessions in 2026-10), to-date is 60
        entry_12 = body["sprints"]["2026-12"]
        to_date_12 = entry_12["session_epics_to_date"]
        assert "E" in to_date_12
        assert to_date_12["E"]["session_minutes"] == 60
        assert to_date_12["E"]["model_minutes"] == 60
        assert to_date_12["E"]["input_tokens"] == 5000
        assert to_date_12["E"]["output_tokens"] == 1000

        # 2026-13 entry: E's to-date is 150 (60 + 90)
        entry_13 = body["sprints"]["2026-13"]
        to_date_13 = entry_13["session_epics_to_date"]
        assert "E" in to_date_13
        assert to_date_13["E"]["session_minutes"] == 150
        assert to_date_13["E"]["model_minutes"] == 150
        assert to_date_13["E"]["input_tokens"] == 13000
        assert to_date_13["E"]["output_tokens"] == 2000
    finally:
        conn.close()


@requires_db
def test_range_session_epics_to_date_accumulates_across_sprints():
    """AC2: to-date totals read 60, 60, 105, 195 across consecutive sprints
    2026-10 through 2026-13; each entry's to-date total equals the previous
    entry's to-date total plus the session minutes that ran in between; the
    session-less sprint (2026-11) adds nothing without resetting."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    for sprint in ("2026-10", "2026-11", "2026-12", "2026-13"):
        conn.execute(f"DELETE FROM sprint_metrics.sessions WHERE sprint = '{sprint}'")
        conn.execute(f"DELETE FROM sprint_metrics.board_events WHERE sprint = '{sprint}'")
        conn.execute(f"DELETE FROM sprint_metrics.sprints WHERE name = '{sprint}'")
    conn.commit()

    for sprint, (d_start, d_end) in {
        "2026-10": (date(2026, 10, 1), date(2026, 10, 14)),
        "2026-11": (date(2026, 10, 15), date(2026, 10, 28)),
        "2026-12": (date(2026, 10, 29), date(2026, 11, 11)),
        "2026-13": (date(2026, 11, 12), date(2026, 11, 25)),
    }.items():
        upsert_sprint(conn, sprint, d_start, d_end, "UTC")

    # Story S1: started in 2026-10 with epic E
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s1', 'started', %s, '2026-10', '2026-10-01', 'E')""",
        (datetime(2026, 10, 1, 9, 0, tzinfo=UTC),),
    )
    conn.commit()

    # 60 minutes in 2026-10
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-10-01T10:00:00Z",
            "end": "2026-10-01T11:00:00Z",
            "sprint": "2026-10",
            "model_seconds": 3600,
            "tokens": 6000,
            "input_tokens": 5000,
            "output_tokens": 1000,
        },
    )
    # 45 minutes in 2026-12 (no session in 2026-11)
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-10-30T10:00:00Z",
            "end": "2026-10-30T10:45:00Z",
            "sprint": "2026-12",
            "model_seconds": 2700,
            "tokens": 4500,
            "input_tokens": 4000,
            "output_tokens": 500,
        },
    )
    # 90 minutes in 2026-13
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-11-13T10:00:00Z",
            "end": "2026-11-13T11:30:00Z",
            "sprint": "2026-13",
            "model_seconds": 5400,
            "tokens": 9000,
            "input_tokens": 8000,
            "output_tokens": 1000,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-13"
        )
        assert status == 200

        # To-date totals: 60, 60, 105, 195
        expected = {
            "2026-10": 60,
            "2026-11": 60,
            "2026-12": 105,
            "2026-13": 195,
        }
        for sprint_label, expected_minutes in expected.items():
            entry = body["sprints"][sprint_label]
            to_date = entry["session_epics_to_date"]
            assert "E" in to_date, f"E missing from {sprint_label} to-date"
            assert (
                to_date["E"]["session_minutes"] == expected_minutes
            ), f"{sprint_label}: expected {expected_minutes}, got {to_date['E']['session_minutes']}"
    finally:
        conn.close()


@requires_db
def test_range_session_epics_to_date_equals_sum_of_per_story():
    """AC3: for every epic shown, its to-date session minutes, by-role
    minutes, model minutes and tokens each equal the sum of the
    corresponding per-story to-date totals of its stories."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    for sprint in ("2026-10", "2026-13"):
        conn.execute(f"DELETE FROM sprint_metrics.sessions WHERE sprint = '{sprint}'")
        conn.execute(f"DELETE FROM sprint_metrics.board_events WHERE sprint = '{sprint}'")
        conn.execute(f"DELETE FROM sprint_metrics.sprints WHERE name = '{sprint}'")
    conn.commit()

    upsert_sprint(conn, "2026-10", date(2026, 10, 1), date(2026, 10, 14), "UTC")
    upsert_sprint(conn, "2026-13", date(2026, 12, 15), date(2026, 12, 28), "UTC")

    # Two stories of epic E, with started events in 2026-10
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s1', 'started', %s, '2026-10', '2026-10-01', 'E')""",
        (datetime(2026, 10, 1, 9, 0, tzinfo=UTC),),
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, epic)
           VALUES ('s2', 'started', %s, '2026-10', '2026-10-01', 'E')""",
        (datetime(2026, 10, 1, 10, 0, tzinfo=UTC),),
    )
    conn.commit()

    # S1: 30 min in 2026-10 (Developer), 20 min in 2026-13 (QA Engineer)
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "Developer",
            "start": "2026-10-01T10:00:00Z",
            "end": "2026-10-01T10:30:00Z",
            "sprint": "2026-10",
            "model_seconds": 1800,
            "tokens": 3000,
            "input_tokens": 2500,
            "output_tokens": 500,
        },
    )
    upsert_session(
        conn,
        {
            "card": "s1",
            "role": "QA Engineer",
            "start": "2026-12-16T10:00:00Z",
            "end": "2026-12-16T10:20:00Z",
            "sprint": "2026-13",
            "model_seconds": 1200,
            "tokens": 2000,
            "input_tokens": 1800,
            "output_tokens": 200,
        },
    )
    # S2: 10 min in 2026-10 (Developer)
    upsert_session(
        conn,
        {
            "card": "s2",
            "role": "Developer",
            "start": "2026-10-01T11:00:00Z",
            "end": "2026-10-01T11:10:00Z",
            "sprint": "2026-10",
            "model_seconds": 600,
            "tokens": 1000,
            "input_tokens": 800,
            "output_tokens": 200,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/range?start=2026-13&end=2026-13"
        )
        assert status == 200
        entry = body["sprints"]["2026-13"]

        # Compute expected per-story to-date from raw data:
        # S1 to-date: 50 min total (30 + 20), Developer 30, QA Engineer 20,
        #   model 50 min (3000s), input 4300, output 700
        # S2 to-date: 10 min, Developer 10, model 10 min (600s),
        #   input 800, output 200
        # Epic E to-date: 60 min, Developer 40, QA Engineer 20,
        #   model 60 min (3600s), input 5100, output 900

        to_date = entry["session_epics_to_date"]
        assert "E" in to_date
        epic_to_date = to_date["E"]

        # Verify epic to-date equals sum of per-story to-date values
        assert epic_to_date["session_minutes"] == 60  # 50 + 10
        assert epic_to_date["minutes_by_role"] == {"Developer": 40, "QA Engineer": 20}
        assert epic_to_date["model_minutes"] == 60  # 50 + 10
        assert epic_to_date["input_tokens"] == 5100  # 4300 + 800
        assert epic_to_date["output_tokens"] == 900  # 700 + 200
    finally:
        conn.close()


def test_metrics_md_describes_to_date():
    """AC4: docs/metrics.md's Per-epic session time section describes the
    to-date total: same measures across every sprint to date, accumulated,
    gap sprints bridged and not read as zero."""
    path = DOCS_DIR / "metrics.md"
    text = path.read_text()
    section = text[text.index("Per-epic session time") :]
    assert "session_epics_to_date" in section
    assert "to-date" in section.lower() or "to date" in section.lower()
    assert "accumulated" in section
    assert "gap" in section.lower()


def test_service_md_describes_session_epics_to_date():
    """AC4: docs/service.md's /range endpoint table carries a description of
    the session_epics_to_date answer."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    generated = text[text.index("BEGIN:service") : text.index("END:service")]
    assert "session_epics_to_date" in generated
    assert "to-date" in generated
    assert "accumulated" in generated
    assert "gap sprints bridged" in generated


def test_changelog_records_to_date():
    """AC5: CHANGELOG.md's [Unreleased] Added section records that /range now
    answers each epic's session time to date."""
    content = CHANGELOG.read_text()
    start = content.index("## [Unreleased]")
    end = content.index("## [", start + 1)
    unreleased = content[start:end]
    added_section = unreleased[unreleased.index("### Added") :]
    assert "session_epics_to_date" in added_section
    assert "to date" in added_section or "to-date" in added_section
