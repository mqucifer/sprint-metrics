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
    """AC3: GET /sprint?label=2024-03 with no events returns 200 and all metrics null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-03")
        assert status == 200
        assert body["throughput"] is None
        assert body["cycle_time_days"] is None
        assert body["lead_time_days"] is None
        assert body["wip_violations"] is None
        assert body["blocked_aging_days"] is None
        assert body["escalation_rate_percent"] is None
        assert body["flags"] is None
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
    """AC5: GET /sprint response has exactly 15 top-level keys and no sprint_date."""
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
            "points_delivered",
            "wip_violations",
            "blocked_aging_days",
            "escalation_rate_percent",
            "escalation_count",
            "first_attempt_rate_percent",
            "first_attempt_numerator",
            "first_attempt_denominator",
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


@requires_db
def test_range_response_metrics_and_keys():
    """AC1: GET /range?start=2024-01&end=2024-02 returns 200, api_version '1',
    sprints has keys '2024-01' and '2024-02' with correct throughput and cycle_time_days."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_range', 'ac2_range')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: card created 2024-01-01, started 2024-01-03, finished 2024-01-07
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: card created 2024-02-01, started 2024-02-03, finished 2024-02-06
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["api_version"] == "1"
        assert set(body["sprints"].keys()) == {"2024-01", "2024-02"}
        assert body["sprints"]["2024-01"]["throughput"] == 1
        assert body["sprints"]["2024-01"]["cycle_time_days"] == 4
        assert body["sprints"]["2024-02"]["throughput"] == 1
        assert body["sprints"]["2024-02"]["cycle_time_days"] == 3
    finally:
        conn.close()


@requires_db
def test_range_prior_and_delta():
    """AC2: 2024-01 has prior=null and delta=null; 2024-02 has prior.throughput=1
    and delta.throughput=0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac2_range_a', 'ac2_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["sprints"]["2024-01"]["prior"] is None
        assert body["sprints"]["2024-01"]["delta"] is None
        assert body["sprints"]["2024-02"]["prior"]["throughput"] == 1
        assert body["sprints"]["2024-02"]["delta"]["throughput"] == 0
    finally:
        conn.close()


@requires_db
def test_range_start_after_end_returns_400():
    """AC3: GET /range?start=2024-02&end=2024-01 returns 400 with error referencing
    the invalid range."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-02&end=2024-01")
        assert status == 400
        assert "error" in body
        assert "range" in body["error"] or "2024-02" in body["error"]
    finally:
        conn.close()


@requires_db
def test_range_sprints_in_chronological_order():
    """AC4: the sprints object has exactly two keys and '2024-01' appears before
    '2024-02' in the serialized JSON (chronological order)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac4_range_a', 'ac4_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02", timeout=5
        ) as resp:
            raw_body = resp.read().decode()

        body = json.loads(raw_body)
        assert len(body["sprints"]) == 2
        assert list(body["sprints"].keys()) == ["2024-01", "2024-02"]
        # Verify in the raw serialized JSON: "2024-01" appears before "2024-02"
        idx_01 = raw_body.index('"2024-01"')
        idx_02 = raw_body.index('"2024-02"')
        assert idx_01 < idx_02
    finally:
        conn.close()


@requires_db
def test_range_first_sprint_prior_and_delta_are_null():
    """AC5: the '2024-01' entry has prior with a JSON null value and delta with a
    JSON null value, because 2024-01 is the first sprint in the range."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac5_range_a', 'ac5_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02", timeout=5
        ) as resp:
            raw_body = resp.read().decode()

        body = json.loads(raw_body)
        # prior must be JSON null (not the string 'null', not an empty object)
        assert body["sprints"]["2024-01"]["prior"] is None
        assert body["sprints"]["2024-01"]["delta"] is None
        # Verify the raw JSON contains 'null' not '"null"' or '{}'
        assert '"prior": null' in raw_body or '"prior":null' in raw_body
    finally:
        conn.close()


@requires_db
def test_range_second_sprint_prior_and_delta_values():
    """AC6: the '2024-02' entry's prior object has throughput=1 and
    cycle_time_days=4, and its delta object has throughput=0 and cycle_time_days=-1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_range_a', 'ac6_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: throughput 1, cycle_time 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: throughput 1, cycle_time 3
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["sprints"]["2024-02"]["prior"]["throughput"] == 1
        assert body["sprints"]["2024-02"]["prior"]["cycle_time_days"] == 4
        assert body["sprints"]["2024-02"]["delta"]["throughput"] == 0
        assert body["sprints"]["2024-02"]["delta"]["cycle_time_days"] == -1
    finally:
        conn.close()


def _get_text(url: str) -> tuple[int, str, str]:
    """GET a URL and return (status, content_type, body_text)."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode()


@requires_db
def test_metrics_cycle_time_line_and_content_type():
    """AC1: GET /metrics after started+finished events returns 200, Content-Type contains text/plain,
    and body has a line starting with sprint_cycle_time_days{sprint="2024-01"} and ending with ' 4'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_metrics'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_metrics",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac1_metrics",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, content_type, body = _get_text(f"http://127.0.0.1:{port}/metrics")
        assert status == 200
        assert "text/plain" in content_type
        lines = body.splitlines()
        cycle_lines = [
            line for line in lines if line.startswith('sprint_cycle_time_days{sprint="2024-01"}')
        ]
        assert len(cycle_lines) == 1
        assert cycle_lines[0].endswith(" 4")
    finally:
        conn.close()


@requires_db
def test_metrics_throughput_lines_both_sprints():
    """AC2: GET /metrics with events in both 2024-01 and 2024-02 contains
    sprint_throughput_cards lines for both sprints."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac2_metrics_a', 'ac2_metrics_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_metrics_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_metrics_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_metrics_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_metrics_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, _, body = _get_text(f"http://127.0.0.1:{port}/metrics")
        assert status == 200
        assert 'sprint_throughput_cards{sprint="2024-01"}' in body
        assert 'sprint_throughput_cards{sprint="2024-02"}' in body
    finally:
        conn.close()


@requires_db
def test_metrics_empty_db_no_metric_lines():
    """AC3: GET /metrics with no events returns 200 and body does not contain
    the substring 'sprint_cycle_time_days'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, _, body = _get_text(f"http://127.0.0.1:{port}/metrics")
        assert status == 200
        assert "sprint_cycle_time_days" not in body
    finally:
        conn.close()


@requires_db
def test_metrics_content_type_and_exact_line():
    """AC4: Content-Type is exactly 'text/plain; version=0.0.4; charset=utf-8' and
    body contains the exact line 'sprint_throughput_cards{sprint="2024-01"} 1'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_metrics'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac4_metrics",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac4_metrics",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, content_type, body = _get_text(f"http://127.0.0.1:{port}/metrics")
        assert status == 200
        assert content_type == "text/plain; version=0.0.4; charset=utf-8"
        lines = body.splitlines()
        assert 'sprint_throughput_cards{sprint="2024-01"} 1' in lines
    finally:
        conn.close()


@requires_db
def test_metrics_seven_lines_per_sprint():
    """AC5: body contains at least seven lines with sprint="2024-01" and
    at least seven lines with sprint="2024-02", one line per metric per sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac5_metrics_a', 'ac5_metrics_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_metrics_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_metrics_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_metrics_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_metrics_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, _, body = _get_text(f"http://127.0.0.1:{port}/metrics")
        assert status == 200
        lines = body.splitlines()
        lines_01 = [line for line in lines if 'sprint="2024-01"' in line]
        lines_02 = [line for line in lines if 'sprint="2024-02"' in line]
        assert len(lines_01) >= 7, f"expected >=7 lines for 2024-01, got {len(lines_01)}"
        assert len(lines_02) >= 7, f"expected >=7 lines for 2024-02, got {len(lines_02)}"
    finally:
        conn.close()


@requires_db
def test_metrics_no_sprint_prefix_when_empty():
    """AC6: body does not contain the substring 'sprint_' when no events are stored.
    No metric lines are emitted for a sprint with no data."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, _, body = _get_text(f"http://127.0.0.1:{port}/metrics")
        assert status == 200
        assert "sprint_" not in body
    finally:
        conn.close()


@requires_db
def test_schema_event_get_returns_200_json_schema():
    """AC1: GET /schema/event returns 200, Content-Type application/json, body is a
    JSON Schema whose $schema is draft 2020-12 and required includes api_version."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/schema/event", timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "api_version" in body["required"]
    finally:
        conn.close()


@requires_db
def test_schema_event_card_and_type_constraints():
    """AC2: schema's properties include a card object whose required includes 'created',
    and the schema constrains type to the six accepted values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card = body["properties"]["card"]
        assert "created" in card["required"]
        type_enum = body["properties"]["type"]["enum"]
        assert set(type_enum) == {
            "started",
            "blocked",
            "unblocked",
            "finished",
            "escalated",
            "attempt_failed",
        }
    finally:
        conn.close()


@requires_db
def test_schema_event_post_returns_405():
    """AC3: POST to /schema/event returns 405."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        data = b"{}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/schema/event",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 405
    finally:
        conn.close()


@requires_db
def test_schema_event_top_level_structure():
    """UX4: top-level $schema, type=object, required includes api_version, card_id,
    type, timestamp, sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert body["type"] == "object"
        for field in ("api_version", "card_id", "type", "timestamp", "sprint"):
            assert field in body["required"]
    finally:
        conn.close()


@requires_db
def test_schema_event_type_enum_exact():
    """AC3+UX4: properties.type.enum is an array of exactly six strings in order:
    started, blocked, unblocked, finished, escalated, attempt_failed."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        assert body["properties"]["type"]["enum"] == [
            "started",
            "blocked",
            "unblocked",
            "finished",
            "escalated",
            "attempt_failed",
        ]
    finally:
        conn.close()


@requires_db
def test_schema_event_card_created_properties():
    """UX6: properties.card has type=object, required includes 'created',
    and properties.card.properties.created has type=string and format=date."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card = body["properties"]["card"]
        assert card["type"] == "object"
        assert "created" in card["required"]
        created = card["properties"]["created"]
        assert created["type"] == "string"
        assert created["format"] == "date"
    finally:
        conn.close()


@requires_db
def test_health_returns_200_when_db_reachable():
    """AC1: GET /health returns 200 when SPRINT_METRICS_DB is reachable."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/health")
        assert status == 200
    finally:
        conn.close()


@requires_db
def test_health_returns_200_with_nonempty_body():
    """AC2: GET /health returns 200 and body has at least one byte when no events stored."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read()
        assert len(body) >= 1
    finally:
        conn.close()


@requires_db
def test_health_body_is_json_object_not_empty():
    """AC3: GET /health body is parseable as JSON and length > 2 (not '{}')."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            body = resp.read().decode()
        parsed = json.loads(body)
        assert isinstance(parsed, dict)
        assert len(body) > 2
    finally:
        conn.close()


@requires_db
def test_health_returns_non_200_when_db_unreachable():
    """AC4: GET /health returns non-200 when the Postgres connection is dead."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    # Close the connection to simulate the DB being killed
    conn.close()

    status, body = _get_json(f"http://127.0.0.1:{port}/health")
    assert status != 200


@requires_db
def test_service_works_without_otel_endpoint(monkeypatch, capsys):
    """AC3: endpoint not set → service responds 200, no error key, no ConnectionError on stderr."""
    import psycopg

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    init_telemetry()

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_telemetry'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac3_telemetry")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        captured = capsys.readouterr()
        assert "ConnectionError" not in captured.err
        assert "connection refused" not in captured.err
    finally:
        conn.close()


@requires_db
def test_post_events_span_name_and_attributes(monkeypatch):
    """AC1: POST /events → exactly one span named 'POST /events' with http.method and http.route."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_span'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_span")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        spans = exporter.get_finished_spans()
        matching = [s for s in spans if "POST" in s.name and "/events" in s.name]
        assert len(matching) == 1
        span = matching[0]
        assert span.attributes["http.method"] == "POST"
        assert span.attributes["http.route"] == "/events"
    finally:
        conn.close()


@requires_db
def test_get_sprint_span_ok_status(monkeypatch):
    """AC2: GET /sprint?label=2024-01 → span has http.method=GET, http.route=/sprint, status OK."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_span'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_span",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200

        spans = exporter.get_finished_spans()
        get_spans = [s for s in spans if s.name == "GET /sprint"]
        assert len(get_spans) == 1
        span = get_spans[0]
        assert span.attributes["http.method"] == "GET"
        assert span.attributes["http.route"] == "/sprint"
        assert span.status.status_code == StatusCode.OK
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_span_error_status(monkeypatch):
    """AC3: POST /events with invalid type 'frobnicated' → span status is not OK."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400

        spans = exporter.get_finished_spans()
        matching = [s for s in spans if "POST" in s.name and "/events" in s.name]
        assert len(matching) == 1
        span = matching[0]
        assert span.status.status_code != StatusCode.OK
    finally:
        conn.close()


@requires_db
def test_get_sprint_without_otel_endpoint_returns_200(monkeypatch):
    """AC4: OTEL endpoint not set → GET /sprint returns 200 with api_version='1'."""
    import psycopg

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    init_telemetry()

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_span'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac4_span",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["api_version"] == "1"
    finally:
        conn.close()


@requires_db
def test_post_valid_event_emits_info_log_record(monkeypatch):
    """AC1: valid POST /events → in-memory log exporter has a record with severity INFO,
    body includes card_id and event type."""
    import psycopg
    from opentelemetry._logs import SeverityNumber
    from opentelemetry.sdk._logs.export.in_memory_log_exporter import InMemoryLogExporter

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    log_exporter = InMemoryLogExporter()
    init_telemetry(log_exporter=log_exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="c1", event_type="started")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        logs = log_exporter.get_finished_logs()
        matching = [
            ld
            for ld in logs
            if "c1" in (ld.log_record.body or "") and "started" in (ld.log_record.body or "")
        ]
        assert len(matching) >= 1
        assert matching[0].log_record.severity_number == SeverityNumber.INFO
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_emits_error_log_record(monkeypatch):
    """AC2: invalid type POST /events → in-memory log exporter has a record with severity ERROR,
    body includes the invalid type value."""
    import psycopg
    from opentelemetry._logs import SeverityNumber
    from opentelemetry.sdk._logs.export.in_memory_log_exporter import InMemoryLogExporter

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    log_exporter = InMemoryLogExporter()
    init_telemetry(log_exporter=log_exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400

        logs = log_exporter.get_finished_logs()
        matching = [ld for ld in logs if "frobnicated" in (ld.log_record.body or "")]
        assert len(matching) >= 1
        assert matching[0].log_record.severity_number >= SeverityNumber.ERROR
    finally:
        conn.close()


@requires_db
def test_trend_cycle_time_three_sprints():
    """AC1: GET /trend?metric=cycle_time_days&start=2024-02&end=2024-04 returns
    200 with three entries: 2024-02 value 3, 2024-03 value null, 2024-04 value 6."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_trend_a', 'ac1_trend_b', 'ac1_trend_c', 'ac1_trend_d')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card, cycle 4 (created 01-01, started 01-02, finished 01-06)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: two cards, each cycle 3 (created 02-01, started 02-02, finished 02-05)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_b",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_c",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_c",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        # 2024-04: one card, cycle 6 (created 04-01, started 04-02, finished 04-08)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_d",
                event_type="started",
                timestamp="2024-04-02T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_d",
                event_type="finished",
                timestamp="2024-04-08T15:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-02&end=2024-04",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "1"
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-02", "value": 3}
        assert body["values"][1] == {"sprint": "2024-03", "value": None}
        assert body["values"][2] == {"sprint": "2024-04", "value": 6}
    finally:
        conn.close()


@requires_db
def test_trend_empty_db_all_zeros():
    """AC2: GET /trend?metric=throughput&start=2024-01&end=2024-03 on an empty DB
    returns 200 with three entries, all value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-03"
        )
        assert status == 200
        assert body["api_version"] == "1"
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert body["values"][2] == {"sprint": "2024-03", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_invalid_metric_returns_400():
    """AC2: GET /trend?metric=bogus_metric&start=2024-01&end=2024-02 returns 400
    with error containing 'bogus_metric'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=bogus_metric&start=2024-01&end=2024-02"
        )
        assert status == 400
        assert "bogus_metric" in body["error"]
    finally:
        conn.close()


@requires_db
def test_trend_start_after_end_returns_400():
    """AC4: GET /trend?metric=throughput&start=2024-03&end=2024-01 returns 400
    with error naming both '2024-03' and '2024-01'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-03&end=2024-01"
        )
        assert status == 400
        assert "2024-03" in body["error"]
        assert "2024-01" in body["error"]
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_rate_two_sprints():
    """AC5: GET /trend?metric=first_attempt_rate_percent&start=2024-01&end=2024-02
    returns 200 with two entries: 2024-01 value 100 (one card, attempts=1),
    2024-02 value 0 (one card, attempts=2)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac5_trend_a', 'ac5_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one completed card, default attempts=1 → 100%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: one completed card, attempts=2 → 0%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_b",
                event_type="finished",
                timestamp="2024-02-07T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                attempts=2,
                failure_class="parse",
                failure_role="Developer",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_rate_percent"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["api_version"] == "1"
        assert len(body["values"]) == 2
        assert body["values"][0]["sprint"] == "2024-01"
        assert body["values"][0]["value"] == 100
        assert body["values"][1]["sprint"] == "2024-02"
        assert body["values"][1]["value"] == 0
    finally:
        conn.close()


@requires_db
def test_trend_response_includes_metric_and_span_labels():
    """UX6: GET /trend?metric=cycle_time_days&start=2024-01&end=2024-02 response
    has top-level keys whose values are 'cycle_time_days', '2024-01', '2024-02'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_trend_a', 'ac6_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_b",
                event_type="started",
                timestamp="2024-02-01T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_b",
                event_type="finished",
                timestamp="2024-02-04T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-01&end=2024-02"
        )
        assert status == 200
        values = list(body.values())
        assert "cycle_time_days" in values
        assert "2024-01" in values
        assert "2024-02" in values
    finally:
        conn.close()


@requires_db
def test_trend_six_sprints_zero_fill_empty_sprint():
    """UX7: GET /trend?metric=throughput&start=2024-01&end=2024-06 with no events
    for 2024-03 returns six entries in order, 2024-03 has value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac7_trend_a', 'ac7_trend_b', 'ac7_trend_c', 'ac7_trend_d', 'ac7_trend_e')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Add one finished card to each of 2024-01, 02, 04, 05, 06 (not 03)
        sprints_with_data = ["2024-01", "2024-02", "2024-04", "2024-05", "2024-06"]
        for i, sprint in enumerate(sprints_with_data):
            card_id = f"ac7_trend_{chr(ord('a') + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp=f"{sprint}-03T10:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp=f"{sprint}-07T15:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-06"
        )
        assert status == 200
        assert len(body["values"]) == 6
        expected_order = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
        for entry, label in zip(body["values"], expected_order, strict=True):
            assert entry["sprint"] == label
        assert body["values"][2]["value"] is None
        assert body["values"][0]["value"] == 1
        assert body["values"][1]["value"] == 1
        assert body["values"][3]["value"] == 1
        assert body["values"][4]["value"] == 1
        assert body["values"][5]["value"] == 1
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_rate_integer_not_string_or_float():
    """UX8: GET /trend?metric=first_attempt_rate_percent with 2024-01 attempts=2
    (value 0) and 2024-02 attempts=1 (value 100) returns JSON integers."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac8_trend_a', 'ac8_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card with attempts=2 → 0%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=2,
                failure_class="parse",
                failure_role="Developer",
            ),
        )
        # 2024-02: one card with attempts=1 (default) → 100%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_b",
                event_type="finished",
                timestamp="2024-02-07T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_rate_percent"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["values"][0]["sprint"] == "2024-01"
        assert body["values"][0]["value"] == 0
        assert isinstance(body["values"][0]["value"], int)
        assert not isinstance(body["values"][0]["value"], bool)
        assert body["values"][1]["sprint"] == "2024-02"
        assert body["values"][1]["value"] == 100
        assert isinstance(body["values"][1]["value"], int)
        assert not isinstance(body["values"][1]["value"], bool)
    finally:
        conn.close()


@requires_db
def test_schema_trend_get_returns_200_json_schema():
    """AC3: GET /schema/trend returns 200, application/json, correct $schema and required."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/schema/trend", timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "api_version" in body["required"]
    finally:
        conn.close()


@requires_db
def test_trend_response_validates_against_schema():
    """AC4 (UX): a /trend response validates against TREND_SCHEMA with no errors."""
    import jsonschema
    import psycopg

    from sprint_metrics.schema import TREND_SCHEMA

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_schema_a', 'ac4_schema_b', 'ac4_schema_c')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Three sprints with one finished card each (throughput = 1 each)
        for sprint, card_id in [
            ("2024-01", "ac4_schema_a"),
            ("2024-02", "ac4_schema_b"),
            ("2024-03", "ac4_schema_c"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp=f"{sprint}-03T10:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp=f"{sprint}-07T15:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-03"
        )
        assert status == 200
        jsonschema.validate(instance=body, schema=TREND_SCHEMA)
    finally:
        conn.close()


@requires_db
def test_trend_doc_worked_example_matches_service_response():
    """AC4: the trend worked example in docs/formats.md, when its events are stored via
    POST /events and queried via GET /trend, produces a response whose values match
    the example's sprint labels and values exactly."""
    import re
    from pathlib import Path

    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'doc_trend_%'")
    conn.commit()

    text = (Path(__file__).parent.parent / "docs" / "formats.md").read_text()
    section_start = text.index("BEGIN:trend-format")
    section_end = text.index("END:trend-format")
    section_text = text[section_start:section_end]
    match = re.search(r"```json\n(.*?)\n```", section_text, re.DOTALL)
    assert match is not None, "no JSON example found in trend-format section"
    example = json.loads(match.group(1))

    metric = example["metric"]
    start = example["start"]
    end = example["end"]
    expected_values = example["values"]

    port = _start_service(conn, 0)
    try:
        for entry in expected_values:
            sprint = entry["sprint"]
            value = entry["value"]
            if metric == "throughput" and value > 0:
                for i in range(value):
                    card_id = f"doc_trend_{sprint}_{i}"
                    _post_events(
                        f"http://127.0.0.1:{port}/events",
                        _make_event(
                            card_id=card_id,
                            event_type="started",
                            timestamp=f"{sprint}-03T10:00:00Z",
                            sprint=sprint,
                            created=f"{sprint}-01",
                        ),
                    )
                    _post_events(
                        f"http://127.0.0.1:{port}/events",
                        _make_event(
                            card_id=card_id,
                            event_type="finished",
                            timestamp=f"{sprint}-07T15:00:00Z",
                            sprint=sprint,
                            created=f"{sprint}-01",
                        ),
                    )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric={metric}&start={start}&end={end}"
        )
        assert status == 200
        assert body["values"] == expected_values
    finally:
        conn.close()


@requires_db
def test_post_events_returns_503_when_db_unreachable():
    """AC1+AC2: POST /events with unreachable DB returns 503 (not 500),
    body is non-empty and does not contain 'Traceback'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac1_503")
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                raw_body = resp.read().decode()
        except urllib.error.HTTPError as e:
            status = e.code
            raw_body = e.read().decode()
        assert status == 503
        assert status != 500
        assert len(raw_body) > 0
        assert "Traceback" not in raw_body
    finally:
        pass


@requires_db
def test_post_events_recover_after_connection_lost():
    """AC4: after the connection is lost, POST /events succeeds once the database
    is reachable again; subsequent GET /sprint returns throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()
    conn.close()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        started = _make_event(
            card_id="ac4_recover",
            event_type="started",
            timestamp="2024-01-05T09:00:00Z",
            sprint="2024-01",
            created="2024-01-04",
        )
        finished = _make_event(
            card_id="ac4_recover",
            event_type="finished",
            timestamp="2024-01-08T15:00:00Z",
            sprint="2024-01",
            created="2024-01-04",
        )
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", started)
        assert status == 200
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", finished)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["throughput"] == 1
    finally:
        pass


@requires_db
def test_post_events_503_content_type_is_application_json():
    """AC5: 503 response Content-Type header is exactly 'application/json'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac5_503")
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
        assert content_type == "application/json"
    finally:
        pass


@requires_db
def test_post_events_503_body_json_contains_database():
    """AC6: 503 body parsed as JSON is a dict, and at least one value (lowercased)
    contains the substring 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac6_503")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 503
        assert isinstance(body, dict)
        values_lowered = [str(v).lower() for v in body.values()]
        assert any("database" in v for v in values_lowered)
    finally:
        pass


@requires_db
def test_post_events_503_body_has_no_card_id_key():
    """AC7: 503 body parsed as JSON has no top-level key named 'card_id'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac7_503")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 503
        assert "card_id" not in body
    finally:
        pass


@requires_db
def test_get_sprint_returns_503_when_db_unreachable():
    """AC1: GET /sprint?label=2024-01 with unreachable DB returns 503 and non-empty body."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 503
        assert len(body) > 0
    finally:
        pass


@requires_db
def test_get_range_returns_503_when_db_unreachable():
    """AC2: GET /range?start=2024-01&end=2024-02 with unreachable DB returns 503 and non-empty body."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 503
        assert len(body) > 0
    finally:
        pass


@requires_db
def test_get_trend_returns_503_when_db_unreachable():
    """AC3: GET /trend?metric=throughput&start=2024-01&end=2024-02 with unreachable DB
    returns 503 and non-empty body."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-02"
        )
        assert status == 503
        assert len(body) > 0
    finally:
        pass


@requires_db
def test_get_sprint_503_content_type_and_database_in_body():
    """AC6 (UX): GET /sprint?label=2024-01 with unreachable DB returns Content-Type
    'application/json' and body has at least one value containing 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/sprint?label=2024-01", timeout=5
            ) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
            body = json.loads(e.read().decode())
        assert content_type == "application/json"
        assert isinstance(body, dict)
        values_lowered = [str(v).lower() for v in body.values()]
        assert any("database" in v for v in values_lowered)
    finally:
        pass


@requires_db
def test_get_range_invalid_range_400_no_database_in_error():
    """AC7 (UX): GET /range?start=2024-02&end=2024-01 with unreachable DB returns 400,
    Content-Type 'application/json', error contains 'invalid range' but not 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/range?start=2024-02&end=2024-01", timeout=5
            ) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
            body = json.loads(e.read().decode())
        assert content_type == "application/json"
        assert "error" in body
        assert "invalid range" in body["error"]
        assert "database" not in body["error"]
    finally:
        pass


@requires_db
def test_get_trend_503_content_type_and_database_in_body():
    """AC8 (UX): GET /trend?metric=throughput&start=2024-01&end=2024-02 with unreachable
    DB returns Content-Type 'application/json' and body has at least one value
    containing 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-02",
                timeout=5,
            ) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
            body = json.loads(e.read().decode())
        assert content_type == "application/json"
        assert isinstance(body, dict)
        values_lowered = [str(v).lower() for v in body.values()]
        assert any("database" in v for v in values_lowered)
    finally:
        pass


@requires_db
def test_health_reconnects_after_connection_lost():
    """AC1: after the connection is lost and the DB is reachable again,
    GET /health returns 200 (the service reconnected automatically)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/health")
        assert status == 200
    finally:
        pass


@requires_db
def test_sprint_reconnects_after_connection_lost():
    """AC2: after storing events and the connection is lost, GET /sprint?label=2024-01
    returns 200 with throughput=1 (the service reconnected and read the stored data)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_reconnect'")
    conn.commit()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        started = _make_event(
            card_id="ac2_reconnect",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac2_reconnect",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        # Simulate DB restart: close the connection the service is using
        conn.close()

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["throughput"] == 1
    finally:
        pass


@requires_db
def test_events_reconnects_after_connection_lost():
    """AC3: after the connection is lost, POST /events with a valid board event
    returns 200 and the body does not contain a key named 'error'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_reconnect'")
    conn.commit()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        # Verify the service works with a live connection
        event = _make_event(
            card_id="ac3_reconnect",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        # Simulate DB restart: close the connection
        conn.close()

        # POST a new event — the service should reconnect
        event2 = _make_event(
            card_id="c2",
            event_type="started",
            timestamp="2024-01-04T10:00:00Z",
            sprint="2024-01",
            created="2024-01-02",
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event2)
        assert status == 200
        assert "error" not in body
    finally:
        pass


@requires_db
def test_health_returns_503_when_db_stopped():
    """AC4: GET /health returns 503 when the database is unreachable and cannot be reconnected."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    # Use an unreachable URL to simulate the DB being stopped (not yet restarted)
    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/health")
        assert status == 503
    finally:
        pass


@requires_db
def test_post_sprints_valid_returns_200_no_error():
    """AC1: POST /sprints with valid body returns 200, Content-Type application/json, no error key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'ac1_sprints'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        body = {
            "name": "ac1_sprints",
            "start_date": "2024-01-15",
            "end_date": "2024-02-15",
            "timezone": "UTC",
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            parsed = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert "error" not in parsed
    finally:
        conn.close()


@requires_db
def test_post_sprints_missing_name_returns_400():
    """AC2: POST /sprints without 'name' returns 400 with error containing 'name'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        body = {"start_date": "2024-01-15", "end_date": "2024-02-15", "timezone": "UTC"}
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                parsed = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            status = e.code
            parsed = json.loads(e.read().decode())
        assert status == 400
        assert "error" in parsed
        assert "name" in parsed["error"]
    finally:
        conn.close()


@requires_db
def test_post_sprints_invalid_date_returns_400():
    """AC3: POST /sprints with start_date '2024-13-45' returns 400 with error containing '2024-13-45'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        body = {
            "name": "Sprint 18",
            "start_date": "2024-13-45",
            "end_date": "2024-02-15",
            "timezone": "UTC",
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                parsed = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            status = e.code
            parsed = json.loads(e.read().decode())
        assert status == 400
        assert "error" in parsed
        assert "2024-13-45" in parsed["error"]
    finally:
        conn.close()


@requires_db
def test_post_sprints_response_contains_name():
    """UX AC4: POST /sprints on empty sprints table returns 200, Content-Type application/json,
    body has 'name' key with the sprint name, no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        body = {
            "name": "Sprint 18",
            "start_date": "2026-10-07",
            "end_date": "2026-10-07",
            "timezone": "America/Chicago",
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            parsed = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert parsed["name"] == "Sprint 18"
        assert "error" not in parsed
    finally:
        conn.close()


@requires_db
def test_post_sprints_upsert_replaces_existing_row():
    """UX AC5: POST /sprints with existing name updates in place; DB has one row with new start_date."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # First registration
        body1 = {
            "name": "Sprint 18",
            "start_date": "2026-10-07",
            "end_date": "2026-10-07",
            "timezone": "America/Chicago",
        }
        data1 = json.dumps(body1).encode()
        req1 = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data1,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req1, timeout=5) as resp:
            assert resp.status == 200
            resp.read()

        # Upsert with new start_date
        body2 = {
            "name": "Sprint 18",
            "start_date": "2026-10-08",
            "end_date": "2026-10-08",
            "timezone": "UTC",
        }
        data2 = json.dumps(body2).encode()
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data2,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req2, timeout=5) as resp:
            status = resp.status
            resp.read()
        assert status == 200

        # Verify exactly one row with the updated start_date
        rows = conn.execute(
            "SELECT start_date FROM sprint_metrics.sprints WHERE name = %s",
            ("Sprint 18",),
        ).fetchall()
        assert len(rows) == 1
        assert str(rows[0][0]) == "2026-10-08"
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
def test_get_sprint_free_form_label_returns_metrics():
    """AC2: GET /sprint?label=Sprint%2018 after posting a finished event returns
    200, Content-Type application/json, api_version='1', throughput=1, cycle_time_days=4."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_sprint_name'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_sprint_name",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        finished = _make_event(
            card_id="ac2_sprint_name",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sprint?label=Sprint%2018", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "1"
        assert body["throughput"] == 1
        assert body["cycle_time_days"] == 4
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
def test_get_sprint_free_form_label_only_started_event():
    """UX4: GET /sprint?label=Sprint%2018 after only a started event returns
    200, Content-Type application/json, api_version='1', throughput=0,
    and flags has exactly seven keys."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_sprint_name'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="ac4_sprint_name",
            event_type="started",
            timestamp="2024-01-15T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", event)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sprint?label=Sprint%2018", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "1"
        assert body["throughput"] == 0
        expected_flag_keys = {
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "escalation_rate_percent",
            "first_attempt_rate_percent",
        }
        assert set(body["flags"].keys()) == expected_flag_keys
    finally:
        conn.close()


@requires_db
def test_get_sprint_free_form_label_same_day_completion():
    """UX5: GET /sprint?label=Sprint%2018 after started+finished on the same day
    returns 200, throughput=1, cycle_time_days=0, lead_time_days=0,
    first_attempt_rate_percent=100."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_sprint_name'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac5_sprint_name",
            event_type="started",
            timestamp="2026-10-07T10:00:00Z",
            sprint="Sprint 18",
            created="2026-10-07",
        )
        finished = _make_event(
            card_id="ac5_sprint_name",
            event_type="finished",
            timestamp="2026-10-07T20:52:22Z",
            sprint="Sprint 18",
            created="2026-10-07",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=Sprint%2018")
        assert status == 200
        assert body["throughput"] == 1
        assert body["cycle_time_days"] == 0
        assert body["lead_time_days"] == 0
        assert body["first_attempt_rate_percent"] == 100
    finally:
        conn.close()


@requires_db
def test_get_sprint_free_form_label_never_sent():
    """UX6: GET /sprint?label=Never%20Sent with no events returns 200,
    Content-Type application/json, and all metrics null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sprint?label=Never%20Sent", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["throughput"] is None
        assert body["cycle_time_days"] is None
        assert body["first_attempt_rate_percent"] is None
    finally:
        conn.close()


@requires_db
def test_post_attempt_failed_returns_200_no_error():
    """AC1: POST /events with type 'attempt_failed' returns 200, Content-Type
    application/json, and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        event = {
            "api_version": "1",
            "card_id": "ac1_attempt",
            "type": "attempt_failed",
            "timestamp": "2024-01-12T14:00:00Z",
            "sprint": "Sprint 18",
            "attempt_number": 1,
            "failure_class": "parse",
            "failure_role": "Developer",
            "card": {"created": "2024-01-10"},
        }
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
def test_sprint_first_attempt_rate_zero_with_attempt_failed():
    """AC2: after started + attempt_failed + finished, GET /sprint returns
    first_attempt_rate_percent=0 and throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        attempt_failed = {
            "api_version": "1",
            "card_id": "ac2_attempt",
            "type": "attempt_failed",
            "timestamp": "2024-01-12T14:00:00Z",
            "sprint": "Sprint 18",
            "attempt_number": 1,
            "failure_class": "parse",
            "failure_role": "Developer",
            "card": {"created": "2024-01-10"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)

        finished = _make_event(
            card_id="ac2_attempt",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
            attempts=2,
            failure_class="parse",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=Sprint%2018")
        assert status == 200
        assert body["first_attempt_rate_percent"] == 0
        assert body["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_failure_breakdown_with_multiple_attempts():
    """UX5: after started + six attempt_failed + finished (attempts 7),
    GET /sprint returns first_attempt_rate_percent=0, throughput=1, and
    failure_breakdown with exactly one element."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac5_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        failure_classes = ["VERIFY", "SCHEMA", "VERIFY", "TEST", "SCHEMA", "VERIFY"]
        for i, fc in enumerate(failure_classes, start=1):
            event = {
                "api_version": "1",
                "card_id": "ac5_attempt",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "Sprint 18",
                "attempt_number": i,
                "failure_class": fc,
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac5_attempt",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
            attempts=7,
            failure_class="VERIFY",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=Sprint%2018")
        assert status == 200
        assert body["first_attempt_rate_percent"] == 0
        assert body["throughput"] == 1
        assert body["failure_breakdown"] == [{"class": "VERIFY", "role": "Developer", "count": 1}]
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
def test_range_registered_sprints_chronological_order():
    """AC1: Range with registered sprints whose lexicographic order differs from
    chronological order returns keys in start_date order."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac1_rs_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac1_rs_%'")
    conn.commit()

    upsert_sprint(conn, "ac1_rs_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac1_rs_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")
    upsert_sprint(conn, "ac1_rs_10", date(2024, 3, 1), date(2024, 3, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        for sprint, card_id in [
            ("ac1_rs_1", "ac1_rs_c1"),
            ("ac1_rs_2", "ac1_rs_c2"),
            ("ac1_rs_10", "ac1_rs_c3"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-03T10:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-07T15:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=ac1_rs_1&end=ac1_rs_10", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            raw_body = resp.read().decode()

        body = json.loads(raw_body)
        assert list(body["sprints"].keys()) == ["ac1_rs_1", "ac1_rs_2", "ac1_rs_10"]
    finally:
        conn.close()


@requires_db
def test_trend_registered_sprints_chronological_order():
    """AC2: Trend with registered sprints whose lexicographic order differs from
    chronological order returns values in start_date order."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac2_ts_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac2_ts_%'")
    conn.commit()

    upsert_sprint(conn, "ac2_ts_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac2_ts_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")
    upsert_sprint(conn, "ac2_ts_10", date(2024, 3, 1), date(2024, 3, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        for sprint, card_id in [
            ("ac2_ts_1", "ac2_ts_c1"),
            ("ac2_ts_2", "ac2_ts_c2"),
            ("ac2_ts_10", "ac2_ts_c3"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-03T10:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-07T15:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=ac2_ts_1&end=ac2_ts_10"
        )
        assert status == 200
        assert body["values"][0]["sprint"] == "ac2_ts_1"
        assert body["values"][1]["sprint"] == "ac2_ts_2"
        assert body["values"][2]["sprint"] == "ac2_ts_10"
    finally:
        conn.close()


@requires_db
def test_range_registered_start_after_end_returns_400():
    """AC3: GET /range with registered sprints where start.start_date > end.start_date
    returns 400 with error referencing the invalid range."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac3_rs_%'")
    conn.commit()

    upsert_sprint(conn, "ac3_rs_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac3_rs_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=ac3_rs_2&end=ac3_rs_1")
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str)
        assert "invalid range" in body["error"] or "ac3_rs_2" in body["error"]
    finally:
        conn.close()


@requires_db
def test_sprint_started_no_finished_returns_zeros():
    """AC1: a started event with no finished event returns zeros, not nulls."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_null'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-05'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_null",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-05",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sprint?label=2024-05", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["throughput"] == 0
        assert body["cycle_time_days"] == 0
        assert body["lead_time_days"] == 0
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_returns_all_nulls():
    """AC3 (UX): no events for the sprint returns all metrics null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sprint?label=2026-11", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "1"
        assert body["throughput"] is None
        assert body["cycle_time_days"] is None
        assert body["lead_time_days"] is None
        assert body["failure_breakdown"] is None
        assert body["top_failure_causes"] is None
        assert body["flags"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_same_day_completion_with_failure_data():
    """AC4 (UX): same-day completion with failure data returns computed values, not nulls."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_null'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac4_null",
            event_type="started",
            timestamp="2026-10-07T13:14:07Z",
            sprint="2026-10",
            created="2026-10-07",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        finished = _make_event(
            card_id="ac4_null",
            event_type="finished",
            timestamp="2026-10-07T20:52:22Z",
            sprint="2026-10",
            created="2026-10-07",
            attempts=7,
            failure_class="VERIFY",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2026-10")
        assert status == 200
        assert body["throughput"] == 1
        assert body["cycle_time_days"] == 0
        assert isinstance(body["failure_breakdown"], list)
        assert len(body["failure_breakdown"]) == 1
        assert body["first_attempt_rate_percent"] == 0
    finally:
        conn.close()


@requires_db
def test_range_two_sprints_with_events_correct_metrics_and_prior():
    """AC1: Range with two known sprints returns correct throughput, cycle_time,
    prior, and delta in chronological order."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_range_ok_a', 'ac1_range_ok_b')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created 2024-01-01, started 2024-01-03, finished 2024-01-07
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: created 2024-02-01, started 2024-02-03, finished 2024-02-06
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["2024-01", "2024-02"]
        assert sprints["2024-01"]["throughput"] == 1
        assert sprints["2024-01"]["cycle_time_days"] == 4
        assert sprints["2024-02"]["throughput"] == 1
        assert sprints["2024-02"]["cycle_time_days"] == 3
        assert sprints["2024-02"]["prior"]["throughput"] == 1
        assert sprints["2024-02"]["prior"]["cycle_time_days"] == 4
        assert sprints["2024-02"]["delta"]["throughput"] == 0
        assert sprints["2024-02"]["delta"]["cycle_time_days"] == -1
    finally:
        conn.close()


@requires_db
def test_range_single_sprint_prior_and_delta_null():
    """AC2: Range with one known sprint returns throughput=1, prior=null, delta=null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_range_single'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_single",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_single",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["2024-01"]
        assert sprints["2024-01"]["throughput"] == 1
        assert sprints["2024-01"]["prior"] is None
        assert sprints["2024-01"]["delta"] is None
    finally:
        conn.close()


@requires_db
def test_range_null_metrics_for_sprints_without_events():
    """AC3 (UX): Range spanning three sprints where only the first has events
    returns null metrics for the gap sprints and computed metrics for the known one."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_range_null_a'")
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_null_a",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_null_a",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # 2026-11 and 2026-12 have no events

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["2026-10", "2026-11", "2026-12"]
        assert sprints["2026-10"]["throughput"] == 1
        assert sprints["2026-11"]["throughput"] is None
        assert sprints["2026-11"]["cycle_time_days"] is None
        assert sprints["2026-11"]["failure_breakdown"] is None
        assert sprints["2026-12"]["throughput"] is None
    finally:
        conn.close()


@requires_db
def test_range_known_sprint_after_unknown_prior_gets_null_prior_and_delta():
    """AC4 (UX): 2026-10 and 2026-12 have events, 2026-11 does not. The 2026-12
    entry has prior=null and delta=null because its preceding sprint is unknown."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_range_null_a', 'ac4_range_null_b')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_a",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_a",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # Sprint 2026-12: one completed card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_b",
                event_type="started",
                timestamp="2026-12-01T09:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_b",
                event_type="finished",
                timestamp="2026-12-03T15:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        # 2026-11 has no events

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2026-11"]["throughput"] is None
        assert sprints["2026-12"]["prior"] is None
        assert sprints["2026-12"]["delta"] is None
    finally:
        conn.close()


@requires_db
def test_trend_all_sprints_have_events_returns_integers():
    """AC1: GET /trend?metric=cycle_time_days&start=2024-01&end=2024-02 with events
    in both sprints returns 200, Content-Type application/json, and the values array
    has exactly 2 entries: 2024-01 value 4, 2024-02 value 3."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_trend_ok_a', 'ac1_trend_ok_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created 2024-01-01, started 2024-01-02, finished 2024-01-06 → cycle 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: created 2024-02-01, started 2024-02-02, finished 2024-02-05 → cycle 3
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_b",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 4}
        assert body["values"][1] == {"sprint": "2024-02", "value": 3}
    finally:
        conn.close()


@requires_db
def test_trend_gap_sprint_returns_null():
    """AC3: GET /trend?metric=cycle_time_days&start=2026-10&end=2026-12 with events
    in 2026-10 and 2026-12 but not 2026-11 returns 200, Content-Type application/json,
    values array has exactly 3 entries: 2026-10 value 4, 2026-11 value null, 2026-12 value 2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac3_trend_gap_a', 'ac3_trend_gap_b')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: created 2026-10-07, started 2026-10-07, finished 2026-10-11 → cycle 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_a",
                event_type="started",
                timestamp="2026-10-07T10:00:00Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_a",
                event_type="finished",
                timestamp="2026-10-11T15:00:00Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # Sprint 2026-12: created 2026-12-01, started 2026-12-01, finished 2026-12-03 → cycle 2
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_b",
                event_type="started",
                timestamp="2026-12-01T10:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_b",
                event_type="finished",
                timestamp="2026-12-03T15:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        # Sprint 2026-11: no events

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2026-10&end=2026-12",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2026-10", "value": 4}
        assert body["values"][1] == {"sprint": "2026-11", "value": None}
        assert body["values"][2] == {"sprint": "2026-12", "value": 2}
    finally:
        conn.close()


@requires_db
def test_trend_single_sprint_with_events_returns_integer():
    """AC4: GET /trend?metric=throughput&start=2026-10&end=2026-10 with events in
    2026-10 returns 200, values array has exactly 1 entry, sprint 2026-10 value is
    integer 1 (not null)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_trend_single'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card, started and finished same day
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_trend_single",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_trend_single",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2026-10&end=2026-10"
        )
        assert status == 200
        assert len(body["values"]) == 1
        assert body["values"][0]["sprint"] == "2026-10"
        assert body["values"][0]["value"] == 1
        assert isinstance(body["values"][0]["value"], int)
        assert not isinstance(body["values"][0]["value"], bool)
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_two_causes():
    """AC1: GET /range with two completed cards having distinct failure causes
    returns failure_breakdown with exactly two objects."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_fb_a', 'ac1_fb_b')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=3,
                failure_class="parse",
                failure_role="Developer",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_b",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_b",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=2,
                failure_class="check",
                failure_role="Code Reviewer",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        fb = body["sprints"]["2024-01"]["failure_breakdown"]
        assert len(fb) == 2
        assert {"class": "parse", "role": "Developer", "count": 1} in fb
        assert {"class": "check", "role": "Code Reviewer", "count": 1} in fb
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_empty_when_first_attempt():
    """AC2: GET /range with a single completed card (attempts=1) returns
    failure_breakdown as an empty array."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_fb'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_fb",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_fb",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["failure_breakdown"] == []
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_not_truncated_to_three():
    """AC3 (UX): GET /range with four completed cards each having a distinct
    (failure_class, failure_role) pair returns failure_breakdown with exactly 4 objects."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac3_fb_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        cards = [
            ("ac3_fb_c1", "PARSE", "Code Reviewer", 3),
            ("ac3_fb_c2", "VERIFY", "Developer", 7),
            ("ac3_fb_c3", "SCHEMA", "Architect", 2),
            ("ac3_fb_c4", "SCHEMA", "Developer", 4),
        ]
        for card_id, fc, fr, attempts in cards:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2026-10-07T13:14:07Z",
                    sprint="2026-10",
                    created="2026-10-07",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2026-10-07T20:52:22Z",
                    sprint="2026-10",
                    created="2026-10-07",
                    attempts=attempts,
                    failure_class=fc,
                    failure_role=fr,
                ),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        fb = body["sprints"]["2026-10"]["failure_breakdown"]
        assert len(fb) == 4
        assert {"class": "PARSE", "role": "Code Reviewer", "count": 1} in fb
        assert {"class": "VERIFY", "role": "Developer", "count": 1} in fb
        assert {"class": "SCHEMA", "role": "Architect", "count": 1} in fb
        assert {"class": "SCHEMA", "role": "Developer", "count": 1} in fb
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_and_top_failure_causes_coexist():
    """AC4 (UX): GET /range with one completed card (VERIFY/Developer, attempts 7)
    returns both failure_breakdown (array with one object) and top_failure_causes
    (object with VERIFY mapping to 1)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_fb'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_fb",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_fb",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
                attempts=7,
                failure_class="VERIFY",
                failure_role="Developer",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        entry = body["sprints"]["2026-10"]
        assert entry["failure_breakdown"] == [{"class": "VERIFY", "role": "Developer", "count": 1}]
        assert entry["top_failure_causes"] == {"VERIFY": 1}
        assert len(entry["failure_breakdown"]) == 1
    finally:
        conn.close()


@requires_db
def test_sprint_response_includes_points_first_attempt_and_escalation_count():
    """AC1/AC6: after POSTing started+finished+escalated for a card with points 5,
    GET /sprint returns the four new fields with correct values alongside existing keys."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_new_fields'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_new_fields",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            points=5,
        )
        finished = _make_event(
            card_id="ac1_new_fields",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        escalated = _make_event(
            card_id="ac1_new_fields",
            event_type="escalated",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)
        _post_events(f"http://127.0.0.1:{port}/events", escalated)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["points_delivered"] == 5
        assert body["first_attempt_numerator"] == 1
        assert body["first_attempt_denominator"] == 1
        assert body["escalation_count"] == 1
        assert "throughput" in body
        assert "first_attempt_rate_percent" in body
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_new_fields_are_null():
    """AC2/AC7: no events stored for sprint 2026-11, GET /sprint returns 200
    and the four new fields are null, matching the existing null pattern."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2026-11")
        assert status == 200
        assert body["points_delivered"] is None
        assert body["first_attempt_numerator"] is None
        assert body["first_attempt_denominator"] is None
        assert body["escalation_count"] is None
        assert body["throughput"] is None
        assert body["first_attempt_rate_percent"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_escalations_counted_without_completions():
    """AC3: one started event (no finished) and two escalated events for sprint 2024-01,
    GET /sprint returns points_delivered=0, first_attempt_numerator=0,
    first_attempt_denominator=0, escalation_count=2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_esc'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac3_esc",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        esc1 = _make_event(
            card_id="ac3_esc",
            event_type="escalated",
            timestamp="2024-01-04T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        esc2 = _make_event(
            card_id="ac3_esc",
            event_type="escalated",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", esc1)
        _post_events(f"http://127.0.0.1:{port}/events", esc2)

        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 200
        assert body["points_delivered"] == 0
        assert body["first_attempt_numerator"] == 0
        assert body["first_attempt_denominator"] == 0
        assert body["escalation_count"] == 2
    finally:
        conn.close()


@requires_db
def test_range_includes_points_first_attempt_and_escalation_count():
    """AC4: 2024-01 has one finished card (points 5, attempts 1) and one escalated event;
    2024-02 has two finished cards (points 3 and 2, both attempts 1) and one escalated event.
    GET /range returns correct values per sprint with existing keys still present."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_range_a', 'ac4_range_b', 'ac4_range_c')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: one finished card (points 5, attempts 1)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                points=5,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="escalated",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: two finished cards (points 3 and 2, both attempts 1)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=3,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_c",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=2,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_c",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="escalated",
                timestamp="2024-02-05T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        s01 = body["sprints"]["2024-01"]
        s02 = body["sprints"]["2024-02"]
        # 2024-01: points 5, first-attempt 1/1, escalation 1
        assert s01["points_delivered"] == 5
        assert s01["first_attempt_numerator"] == 1
        assert s01["first_attempt_denominator"] == 1
        assert s01["escalation_count"] == 1
        # 2024-02: points 5 (3+2), first-attempt 2/2, escalation 1
        assert s02["points_delivered"] == 5
        assert s02["first_attempt_numerator"] == 2
        assert s02["first_attempt_denominator"] == 2
        assert s02["escalation_count"] == 1
        # Both entries still contain existing keys and prior and delta
        for s in (s01, s02):
            for key in ("throughput", "cycle_time_days", "prior", "delta"):
                assert key in s
    finally:
        conn.close()


@requires_db
def test_range_null_new_fields_for_sprints_without_events():
    """AC5: sprint 2026-10 has one finished card (points 2, attempts 1);
    sprints 2026-11 and 2026-12 have no stored events. GET /range returns
    2026-10 with values and 2026-11/2026-12 with nulls for the four new fields."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_range_null'")
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_null",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
                points=2,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_null",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        s10 = body["sprints"]["2026-10"]
        s11 = body["sprints"]["2026-11"]
        s12 = body["sprints"]["2026-12"]
        # 2026-10 has values
        assert s10["points_delivered"] == 2
        assert s10["first_attempt_numerator"] == 1
        assert s10["first_attempt_denominator"] == 1
        assert s10["escalation_count"] == 0
        # 2026-11 and 2026-12 have nulls
        for s in (s11, s12):
            assert s["points_delivered"] is None
            assert s["first_attempt_numerator"] is None
            assert s["first_attempt_denominator"] is None
            assert s["escalation_count"] is None
    finally:
        conn.close()
