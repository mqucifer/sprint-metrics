"""Service tests for GET /schema/event and GET /schema/trend."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from service_helpers import (
    SPRINT_METRICS_DB,
    _clean_board_events,  # noqa: F401 (autouse: empties the tables)
    _get_json,
    requires_db,
)

from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


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
    and the schema constrains type to the ten accepted values."""
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
            "superseded",
            "returned",
            "filed",
            "session",
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
    """AC3+UX4: properties.type.enum is an array of exactly ten strings in order:
    started, blocked, unblocked, finished, escalated, attempt_failed, superseded,
    returned, filed, session."""
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
            "superseded",
            "returned",
            "filed",
            "session",
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
