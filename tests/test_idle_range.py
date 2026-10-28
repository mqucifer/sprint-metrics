"""DB-backed tests for the idle-time answer on /range and the idle_minutes measure on /trend.

The idle answer carries the idle time (the time that passed with no session
running) against the sprint's total registered duration, in whole minutes.
"""

from __future__ import annotations

import psycopg
from test_service import (
    SPRINT_METRICS_DB,
    _get_json,
    _make_event,
    _post_events,
    _start_service,
    requires_db,
)

from sprint_metrics.store import init_db


def _register_sprint(conn, name: str, start: str, end: str, timezone: str = "UTC") -> None:
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = %s", (name,))
    conn.execute(
        "INSERT INTO sprint_metrics.sprints (name, start_date, end_date, timezone) "
        "VALUES (%s, %s, %s, %s)",
        (name, start, end, timezone),
    )
    conn.commit()


@requires_db
def test_range_idle_shown_against_duration():
    """AC1: a sprint registered 2024-01-01 to 2024-01-14 in UTC whose events include one
    30-minute session carries idle against the duration — 20160 total, 20130 idle."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'idle1'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()
    _register_sprint(conn, "2024-01", "2024-01-01", "2024-01-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle1", event_type="started", timestamp="2024-01-05T10:00:00Z", sprint="2024-01"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle1", event_type="finished", timestamp="2024-01-05T10:30:00Z", sprint="2024-01"),
        )
        status, body = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        assert status == 200
        entry = body["sprints"]["2024-01"]
        assert entry["idle"]["sprint_duration_minutes"] == 20160
        assert entry["idle"]["idle_minutes"] == 20130
    finally:
        conn.close()


@requires_db
def test_range_idle_null_when_not_registered():
    """AC2: a sprint with events but no registered definition reads idle null (the whole
    span is not reported as idle when no registered span exists)."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'idle2'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-02'")
    conn.commit()
    # Deliberately no row in sprint_metrics.sprints for 2024-02.

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle2", event_type="started", timestamp="2024-02-05T10:00:00Z", sprint="2024-02"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle2", event_type="finished", timestamp="2024-02-05T10:30:00Z", sprint="2024-02"),
        )
        status, body = _get_json(f"{base}/range?start=2024-02&end=2024-02")
        assert status == 200
        entry = body["sprints"]["2024-02"]
        assert entry["idle"] is None
    finally:
        conn.close()


@requires_db
def test_range_idle_null_when_no_session_ran():
    """AC2: a registered sprint in which no card carries a closed session window carries
    the registered duration with idle null (the whole span is not reported as idle)."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'idle3'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()
    _register_sprint(conn, "2024-03", "2024-03-01", "2024-03-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # A card that started but never closed: no closed session window.
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle3", event_type="started", timestamp="2024-03-05T10:00:00Z", sprint="2024-03"),
        )
        status, body = _get_json(f"{base}/range?start=2024-03&end=2024-03")
        assert status == 200
        entry = body["sprints"]["2024-03"]
        assert entry["idle"]["sprint_duration_minutes"] == 20160
        assert entry["idle"]["idle_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_idle_prior_and_delta_carry_idle_minutes():
    """AC6: the flat idle_minutes name appears in each later entry's prior and delta,
    null where a sprint has no data."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('idle4a', 'idle4b')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-04', '2024-05')")
    conn.commit()
    _register_sprint(conn, "2024-04", "2024-04-01", "2024-04-14")
    _register_sprint(conn, "2024-05", "2024-05-01", "2024-05-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-04: a 30-minute session -> idle 20130.
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle4a", event_type="started", timestamp="2024-04-05T10:00:00Z", sprint="2024-04"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle4a", event_type="finished", timestamp="2024-04-05T10:30:00Z", sprint="2024-04"),
        )
        # 2024-05: a 60-minute session -> idle 20100.
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle4b", event_type="started", timestamp="2024-05-05T10:00:00Z", sprint="2024-05"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle4b", event_type="finished", timestamp="2024-05-05T11:00:00Z", sprint="2024-05"),
        )
        status, body = _get_json(f"{base}/range?start=2024-04&end=2024-05")
        assert status == 200
        first = body["sprints"]["2024-04"]
        second = body["sprints"]["2024-05"]
        assert first["idle"]["idle_minutes"] == 20130
        assert first["prior"] is None
        assert first["delta"] is None
        assert second["idle"]["idle_minutes"] == 20100
        assert second["prior"]["idle_minutes"] == 20130
        assert second["delta"]["idle_minutes"] == 20100 - 20130
    finally:
        conn.close()


@requires_db
def test_trend_idle_minutes():
    """AC5: GET /trend for the idle-time measure returns each sprint's idle minutes,
    null where the sprint is not registered or carries no session timestamps."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'idle5'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-06', '2024-07')")
    conn.commit()
    _register_sprint(conn, "2024-06", "2024-06-01", "2024-06-14")
    # 2024-07 deliberately not registered.

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle5", event_type="started", timestamp="2024-06-05T10:00:00Z", sprint="2024-06"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle5", event_type="finished", timestamp="2024-06-05T10:30:00Z", sprint="2024-06"),
        )
        # 2024-07: a session, but the sprint is not registered -> null.
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle5", event_type="started", timestamp="2024-07-05T10:00:00Z", sprint="2024-07"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="idle5", event_type="finished", timestamp="2024-07-05T10:30:00Z", sprint="2024-07"),
        )
        status, body = _get_json(f"{base}/trend?start=2024-06&end=2024-07&metric=idle_minutes")
        assert status == 200
        assert body["metric"] == "idle_minutes"
        assert body["values"] == [
            {"sprint": "2024-06", "value": 20130},
            {"sprint": "2024-07", "value": None},
        ]
    finally:
        conn.close()


def test_range_schema_declares_idle_on_sprint_entry():
    """AC6: SPRINT_RANGE_SCHEMA declares idle as an optional property per sprint entry
    (not in required), with sprint_duration_minutes (integer) and idle_minutes
    (integer or null), and the flat idle_minutes name on prior and delta."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "idle" not in sprint_entry["required"]
    idle = sprint_entry["properties"]["idle"]
    assert idle["type"] == ["object", "null"]
    assert idle["required"] == ["sprint_duration_minutes", "idle_minutes"]
    assert idle["properties"]["sprint_duration_minutes"] == {"type": "integer"}
    assert idle["properties"]["idle_minutes"] == {"type": ["integer", "null"]}
    # The flat name appears in prior and delta.
    prior = sprint_entry["properties"]["prior"]["properties"]
    assert prior["idle_minutes"] == {"type": ["integer", "null"]}
    delta = sprint_entry["properties"]["delta"]["properties"]
    assert delta["idle_minutes"] == {"type": ["integer", "null"]}
