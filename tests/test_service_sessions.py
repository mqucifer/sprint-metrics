"""Service tests for the session event at intake."""

from __future__ import annotations

from service_helpers import (
    SPRINT_METRICS_DB,
    _clean_board_events,  # noqa: F401 (autouse: empties the tables)
    _get_json,
    _make_event,
    _post_events,
    requires_db,
)

from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


@requires_db
def test_post_session_event_with_card_returns_200_and_stores():
    """AC1: a session event in the shape the crew's contract publishes (card, role,
    start, end, model_seconds, tokens) POSTs to /events, gets 200, and the record
    holds the session with the values sent."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE card_id = 'sess_ac1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "sess_ac1",
            "type": "session",
            "timestamp": "2024-01-15T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
            "role": "developer",
            "start": "2024-01-15T09:00:00Z",
            "end": "2024-01-15T10:00:00Z",
            "model_seconds": 3600,
            "tokens": 100000,
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT card_id, role, session_start, session_end, model_seconds, tokens "
            "FROM sprint_metrics.sessions WHERE card_id = 'sess_ac1'"
        ).fetchall()
        assert len(rows) == 1
        card_id, role, start, end, model_seconds, tokens = rows[0]
        assert card_id == "sess_ac1"
        assert role == "developer"
        assert model_seconds == 3600
        assert tokens == 100000
    finally:
        conn.close()


@requires_db
def test_post_session_event_without_card_returns_200_and_stores_null_card():
    """AC2: a session with no card (card_id and card absent from the envelope)
    POSTs to /events, gets 200, and the record holds it with a null card."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE card_id IS NULL AND role = 'qa_ac2'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "type": "session",
            "timestamp": "2024-01-15T10:00:00Z",
            "sprint": "2024-01",
            "role": "qa_ac2",
            "start": "2024-01-15T09:00:00Z",
            "end": "2024-01-15T10:00:00Z",
            "model_seconds": 1800,
            "tokens": 50000,
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT card_id, role, model_seconds, tokens "
            "FROM sprint_metrics.sessions WHERE role = 'qa_ac2' AND sprint = '2024-01'"
        ).fetchall()
        assert len(rows) == 1
        card_id, role, model_seconds, tokens = rows[0]
        assert card_id is None
        assert role == "qa_ac2"
        assert model_seconds == 1800
        assert tokens == 50000
    finally:
        conn.close()


@requires_db
def test_post_session_event_missing_role_returns_400():
    """AC3: a session event with role missing gets 400 naming the problem,
    and the record holds no session."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE card_id = 'sess_ac3'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "sess_ac3",
            "type": "session",
            "timestamp": "2024-01-15T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
            "start": "2024-01-15T09:00:00Z",
            "end": "2024-01-15T10:00:00Z",
            "model_seconds": 3600,
            "tokens": 100000,
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "role" in body["error"]

        rows = conn.execute(
            "SELECT * FROM sprint_metrics.sessions WHERE card_id = 'sess_ac3'"
        ).fetchall()
        assert len(rows) == 0
    finally:
        conn.close()


@requires_db
def test_post_session_event_wrong_type_for_start_returns_400():
    """AC3: a session event with start as an integer (wrong type) gets 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE card_id = 'sess_ac3b'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "sess_ac3b",
            "type": "session",
            "timestamp": "2024-01-15T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
            "role": "developer",
            "start": 12345,
            "end": "2024-01-15T10:00:00Z",
            "model_seconds": 3600,
            "tokens": 100000,
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "start" in body["error"]
    finally:
        conn.close()


@requires_db
def test_nine_event_types_still_accepted_and_unknown_still_400():
    """AC4: the nine existing event types are still accepted, and an unaccepted
    type still answers 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    for t in (
        "started",
        "blocked",
        "unblocked",
        "finished",
        "escalated",
        "attempt_failed",
        "superseded",
        "returned",
        "filed",
    ):
        conn.execute(
            "DELETE FROM sprint_metrics.board_events WHERE card_id = %s", (f"ac4_{t}",)
        )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        for event_type in (
            "started",
            "blocked",
            "unblocked",
            "finished",
            "escalated",
            "attempt_failed",
            "superseded",
            "returned",
            "filed",
        ):
            event = _make_event(card_id=f"ac4_{event_type}", event_type=event_type)
            if event_type == "superseded":
                event["because"] = "sponsor"
            if event_type == "filed":
                event["filer"] = "crew"
            status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
            assert status == 200, f"{event_type} should be accepted, got {status}: {body}"
            assert "error" not in body

        # An unaccepted type still gets 400.
        event = _make_event(card_id="ac4_unknown", event_type="exploded")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "exploded" in body["error"]
    finally:
        conn.close()


@requires_db
def test_session_event_does_not_change_range_or_trend():
    """AC5: a session event for a card in a sprint does not change the other
    /range fields or the /trend response; session_stories carries the
    session's per-story numbers."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id = 'sess_ac5'"
    )
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE card_id = 'sess_ac5'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Post a board event so the sprint has data.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="sess_ac5", event_type="started", sprint="2024-01"),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="sess_ac5", event_type="finished", sprint="2024-01"),
        )

        # Capture /range and /trend before the session.
        status, before = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        status, trend_before = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-01"
        )
        assert status == 200

        # Post a session event.
        session_event = {
            "api_version": "1",
            "card_id": "sess_ac5",
            "type": "session",
            "timestamp": "2024-01-15T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
            "role": "developer",
            "start": "2024-01-15T09:00:00Z",
            "end": "2024-01-15T10:00:00Z",
            "model_seconds": 3600,
            "tokens": 100000,
            "input_tokens": 60000,
            "output_tokens": 40000,
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", session_event)
        assert status == 200

        # Capture /range and /trend after the session.
        status, after = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        # Every /range field except session_stories, session_planning,
        # working_time, cost, story_costs, model_time, and model_time_split
        # is unchanged.
        _session_derived = {
            "session_stories",
            "session_planning",
            "working_time",
            "cost",
            "story_costs",
            "model_time",
            "model_time_split",
        }
        before_fields = {
            k: v for k, v in before["sprints"]["2024-01"].items() if k not in _session_derived
        }
        after_fields = {
            k: v for k, v in after["sprints"]["2024-01"].items() if k not in _session_derived
        }
        assert before_fields == after_fields
        # session_stories correctly carries the session's per-story numbers.
        ss = after["sprints"]["2024-01"]["session_stories"]["sess_ac5"]
        assert ss["session_minutes"] == 60
        assert ss["minutes_by_role"] == {"developer": 60}
        assert ss["model_minutes"] == 60
        assert ss["input_tokens"] == 60000
        assert ss["output_tokens"] == 40000
        # /trend is unchanged.
        status, trend_after = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-01"
        )
        assert status == 200
        assert trend_before == trend_after
    finally:
        conn.close()


def test_service_md_post_events_lists_session():
    """AC7: docs/service.md's Endpoints table names 'session' alongside the nine
    existing types in the POST /events row."""
    from pathlib import Path

    content = (Path(__file__).parent.parent / "docs" / "service.md").read_text()
    # Find the POST /events row in the Endpoints table.
    lines = content.splitlines()
    post_events_rows = [
        line for line in lines if "POST" in line and "/events" in line
    ]
    assert post_events_rows, "No POST /events row found in Endpoints table"
    row = post_events_rows[0]
    assert "session" in row
    for t in (
        "started",
        "blocked",
        "unblocked",
        "finished",
        "escalated",
        "attempt_failed",
        "superseded",
        "returned",
        "filed",
    ):
        assert t in row, f"{t!r} not in POST /events row"
