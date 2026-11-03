"""Tests for the per-epic session-time answer: each epic's in-sprint session minutes, by role, model minutes, and tokens, summed over its stories."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, date, datetime

import pytest

from sprint_metrics.service import _start_service
from sprint_metrics.session_epics import calculate_session_epics
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
