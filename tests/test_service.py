"""Tests for the stateful HTTP service in sprint_metrics.service."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

from sprint_metrics.service import _start_service, run
from sprint_metrics.store import init_db

SPRINT_METRICS_DB = os.environ.get("SPRINT_METRICS_DB")

requires_db = pytest.mark.skipif(SPRINT_METRICS_DB is None, reason="SPRINT_METRICS_DB not set")


def _make_event(
    card_id: str = "c1",
    event_type: str = "started",
    timestamp: str = "2024-01-03T10:00:00Z",
    sprint: str = "2024-01",
    created: str = "2024-01-01",
    **card_extra: object,
) -> dict:
    """Build a valid event dict for POST /events."""
    return {
        "api_version": "1",
        "card_id": card_id,
        "type": event_type,
        "timestamp": timestamp,
        "sprint": sprint,
        "card": {"created": created, **card_extra},
    }


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

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["throughput"] == 1
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


def test_service_exits_nonzero_on_unreachable_db(capsys):
    """AC4: SPRINT_METRICS_DB pointing to unreachable Postgres: non-zero exit,
    stderr references the database connection."""
    exit_code = run("postgresql://user:pass@127.0.0.1:19999/nonexistent")
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "database" in captured.err.lower() or "connection" in captured.err.lower()


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
