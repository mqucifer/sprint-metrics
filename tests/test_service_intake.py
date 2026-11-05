"""Service tests for POST /events: accepted and refused events, the sprint field, points, and re-sent events."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

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
def test_post_valid_event_returns_200_no_error():
    """AC1: POST /events with a valid started event returns 200 and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_test'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_test")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_duplicate_finished_event_idempotent():
    """AC2: POSTing the same finished event twice results in throughput=1, not 2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_test'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_test",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac2_test",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)
        # Post the identical finished event again
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", finished)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_returns_400():
    """AC3: POST /events with type 'invalid_type' returns 400 with error naming the type."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="invalid_type")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "invalid_type" in body["error"]
    finally:
        conn.close()


@requires_db
def test_post_response_content_type_and_no_error():
    """AC5: POST valid event → Content-Type is application/json, body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_test'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac5_test")
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_frobnicated_error_contains_type():
    """AC6: POST with type 'frobnicated' → error string contains 'frobnicated'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "frobnicated" in body["error"]
    finally:
        conn.close()


@requires_db
def test_post_events_free_form_sprint_name_returns_200():
    """AC1: POST /events with sprint='Sprint 18' returns 200 and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_sprint_name'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_sprint_name", sprint="Sprint 18")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_events_empty_sprint_returns_400():
    """AC3: POST /events with sprint='' returns 400 and body has a non-empty 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac3_sprint_name", sprint="")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str) and len(body["error"]) > 0
    finally:
        conn.close()


@requires_db
def test_post_event_with_points_stores_value():
    """AC1+AC2+UX4: POST /events with card.points=5 returns 200, no error key,
    and SELECT points FROM board_events WHERE card_id='453' AND type='started'
    returns exactly one row whose points column holds the integer 5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = '453'")
    conn.commit()
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()
    conn.execute(
        "INSERT INTO sprint_metrics.sprints (name, start_date, end_date, timezone) "
        "VALUES ('Sprint 18', '2026-10-07', '2026-10-07', 'America/Chicago')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "453",
            "type": "started",
            "sprint": "Sprint 18",
            "timestamp": "2026-10-07T13:14:07Z",
            "card": {"created": "2026-10-07", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT points FROM sprint_metrics.board_events WHERE card_id = '453' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 5
    finally:
        conn.close()


@requires_db
def test_post_event_without_points_stores_null():
    """AC3+UX5: POST /events without card.points returns 200, no error key,
    and SELECT points FROM board_events WHERE card_id='455' AND type='started'
    returns exactly one row whose points column is NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = '455'")
    conn.commit()
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()
    conn.execute(
        "INSERT INTO sprint_metrics.sprints (name, start_date, end_date, timezone) "
        "VALUES ('Sprint 18', '2026-10-07', '2026-10-07', 'America/Chicago')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "455",
            "type": "started",
            "sprint": "Sprint 18",
            "timestamp": "2026-10-07T09:15:00Z",
            "card": {"created": "2026-10-06"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT points FROM sprint_metrics.board_events WHERE card_id = '455' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        conn.close()


@requires_db
def test_post_unknown_event_type_still_returns_400():
    """AC4: POST /events with a type that is not one of the nine accepted event
    types answers 400 naming the unknown type."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="f4", event_type="reopened")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "reopened" in body["error"]
    finally:
        conn.close()


@requires_db
def test_post_unknown_event_type_returns_400_naming_type():
    """AC4: POST /events with a type that is not one of the eight accepted event
    types answers 400 naming the unknown type."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="r4", event_type="reopened")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "reopened" in body["error"]
    finally:
        conn.close()


@requires_db
def test_resend_event_fills_null_points_via_service():
    """AC3: POST /events without points, then with points=5: /range shows points_delivered=5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_svc'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event_no_points = {
            "api_version": "1",
            "card_id": "c_svc",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_no_points)
        assert status == 200

        event_with_points = {
            "api_version": "1",
            "card_id": "c_svc",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_with_points)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["points_delivered"] == 5
    finally:
        conn.close()


@requires_db
def test_resend_event_keeps_existing_points_via_service():
    """AC4: POST /events with points=5, then with points=3: /range shows points_delivered=5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_svc2'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event_points_5 = {
            "api_version": "1",
            "card_id": "c_svc2",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_points_5)
        assert status == 200

        event_points_3 = {
            "api_version": "1",
            "card_id": "c_svc2",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01", "points": 3},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_points_3)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["points_delivered"] == 5
    finally:
        conn.close()
