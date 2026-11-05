"""Service tests for POST /sprints."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from service_helpers import (
    SPRINT_METRICS_DB,
    _clean_board_events,  # noqa: F401 (autouse: empties the tables)
    requires_db,
)

from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


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
