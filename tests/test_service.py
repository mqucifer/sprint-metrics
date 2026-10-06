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


@requires_db
def test_sprint_response_metrics_and_content_type():
    """AC1: GET /sprint?label=2024-01 after POSTing started+finished for c1
    returns 200, Content-Type application/json, and the expected metric values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_sprint'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_sprint",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac1_sprint",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sprint?label=2024-01", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "1"
        assert body["throughput"] == 1
        assert body["cycle_time_days"] == 4
        assert body["lead_time_days"] == 6
        for key, value in body["flags"].items():
            assert isinstance(value, bool), f"flags[{key!r}] is {type(value).__name__}, not bool"
    finally:
        conn.close()


@requires_db
def test_sprint_excludes_card_finishing_in_different_sprint():
    """AC2: c2's finished event is in sprint 2024-02, so GET /sprint?label=2024-01
    reports throughput 0 for that card."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_sprint'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_sprint",
            event_type="started",
            timestamp="2024-01-20T10:00:00Z",
            sprint="2024-01",
            created="2024-01-05",
        )
        finished = _make_event(
            card_id="ac2_sprint",
            event_type="finished",
            timestamp="2024-02-10T14:00:00Z",
            sprint="2024-02",
            created="2024-01-05",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["throughput"] == 0
    finally:
        conn.close()


@requires_db
def test_sprint_empty_db_returns_all_zeros():
    """AC3: GET /sprint?label=2024-03 with no events returns 200, all metrics 0,
    and every flag false."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-03")
        assert status == 200
        assert body["throughput"] == 0
        assert body["cycle_time_days"] == 0
        assert body["lead_time_days"] == 0
        assert body["wip_violations"] == 0
        assert body["blocked_aging_days"] == 0
        assert body["escalation_rate_percent"] == 0
        for key, value in body["flags"].items():
            assert value is False, f"flags[{key!r}] is {value!r}, expected False"
    finally:
        conn.close()


@requires_db
def test_sprint_data_survives_reconnect():
    """AC4: events stored via one connection are still returned when a new
    connection (simulating a process restart) queries them."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_sprint'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac4_sprint",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac4_sprint",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)
    finally:
        conn.close()

    # Simulate restart: open a fresh connection and query
    conn2 = psycopg.connect(SPRINT_METRICS_DB)
    port2 = _start_service(conn2, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port2}/sprint?label=2024-01")
        assert status == 200
        assert body["throughput"] == 1
    finally:
        conn2.close()


@requires_db
def test_sprint_response_has_exactly_eleven_keys_no_sprint_date():
    """AC5: GET /sprint response has exactly 11 top-level keys and no sprint_date."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_sprint'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac5_sprint",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac5_sprint",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        expected_keys = {
            "api_version",
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "escalation_rate_percent",
            "first_attempt_rate_percent",
            "failure_breakdown",
            "top_failure_causes",
            "flags",
        }
        assert set(body.keys()) == expected_keys
        assert "sprint_date" not in body
    finally:
        conn.close()


@requires_db
def test_sprint_flags_has_exactly_seven_boolean_keys():
    """AC6: the flags object has exactly 7 keys, all with boolean values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac6_sprint'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac6_sprint",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac6_sprint",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        flags = body["flags"]
        expected_flag_keys = {
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "escalation_rate_percent",
            "first_attempt_rate_percent",
        }
        assert set(flags.keys()) == expected_flag_keys
        for key, value in flags.items():
            assert isinstance(value, bool), f"flags[{key!r}] is {type(value).__name__}, not bool"
    finally:
        conn.close()


@requires_db
def test_sprint_throughput_and_cycle_zero_for_cross_sprint_card():
    """AC7: c2's finished event is in sprint 2024-02, so GET /sprint?label=2024-01
    reports throughput 0 and cycle_time_days 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac7_sprint'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac7_sprint",
            event_type="started",
            timestamp="2024-01-20T10:00:00Z",
            sprint="2024-01",
            created="2024-01-05",
        )
        finished = _make_event(
            card_id="ac7_sprint",
            event_type="finished",
            timestamp="2024-02-10T14:00:00Z",
            sprint="2024-02",
            created="2024-01-05",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["throughput"] == 0
        assert body["cycle_time_days"] == 0
    finally:
        conn.close()
