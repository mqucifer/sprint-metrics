"""Service tests for GET /health, startup without a database, the 503 answers, and reconnecting."""

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

from sprint_metrics.service import _start_service, run
from sprint_metrics.store import init_db


def test_service_exits_nonzero_on_unreachable_db(capsys):
    """AC4: SPRINT_METRICS_DB pointing to unreachable Postgres: non-zero exit,
    stderr references the database connection."""
    exit_code = run("postgresql://user:pass@127.0.0.1:19999/nonexistent")
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "database" in captured.err.lower() or "connection" in captured.err.lower()


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
    is reachable again; subsequent GET /range returns throughput=1."""
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

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["throughput"] == 1
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
