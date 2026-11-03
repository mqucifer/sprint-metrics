"""DB-backed tests for the idle-time answer on /range and the idle_minutes measure on /trend.

The idle answer carries the sprint's idle time — the registered sprint span
minus the sprint's session minutes, from the same session records that feed
the working time — in whole minutes, in the sprint's registered timezone; a
sprint with no session records, or with no registered definition, reads null
(no data, not zero).
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


def _session_event(
    card_id: str | None, sprint: str, start: str, end: str, role: str = "developer"
) -> dict:
    """A session event in the shape the crew's contract publishes.

    Carded sessions carry card_id and card; a card-less session carries neither
    (card_id and card are optional when the session has no card)."""
    event = {
        "api_version": "1",
        "type": "session",
        "timestamp": start,
        "sprint": sprint,
        "role": role,
        "start": start,
        "end": end,
    }
    if card_id is not None:
        event["card_id"] = card_id
        event["card"] = {"created": "2024-01-01"}
    return event


@requires_db
def test_range_idle_shown_against_duration():
    """AC1: a sprint registered 2024-01-01 to 2024-01-14 in UTC (a span of 20160
    minutes) whose session records total 45 session minutes (27 story, 10
    planning, 8 card-less) carries idle 20115 — the registered span minus the
    same session minutes the working time uses — and the working time and the
    idle time agree from the same session records (45 + 20115 = 20160)."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-01'")
    conn.commit()
    _register_sprint(conn, "2024-01", "2024-01-01", "2024-01-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # Establish the story's start (the planning/delivery boundary).
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle1",
                event_type="started",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
            ),
        )
        # 27 minutes of story session (delivery, from the story's start on).
        _post_events(
            f"{base}/events",
            _session_event("idle1", "2024-01", "2024-01-05T10:00:00Z", "2024-01-05T10:27:00Z"),
        )
        # 10 minutes of planning (before the story's start).
        _post_events(
            f"{base}/events",
            _session_event("idle1", "2024-01", "2024-01-05T09:50:00Z", "2024-01-05T10:00:00Z"),
        )
        # 8 minutes of card-less session.
        _post_events(
            f"{base}/events",
            _session_event(None, "2024-01", "2024-01-06T14:00:00Z", "2024-01-06T14:08:00Z"),
        )
        status, body = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        assert status == 200
        entry = body["sprints"]["2024-01"]
        assert entry["idle"]["sprint_duration_minutes"] == 20160
        assert entry["idle"]["idle_minutes"] == 20115
        # The working time and the idle time agree from the same session records.
        assert entry["working_time"]["total"] == 45
        assert entry["idle"]["idle_minutes"] + entry["working_time"]["total"] == 20160
    finally:
        conn.close()


@requires_db
def test_range_idle_null_when_not_registered():
    """AC3: a sprint holding session records (45 session minutes) but with no
    registered start and end dates reads the idle answer null (no registered
    span to subtract from), while the working-time answer still reads 45 from
    the session records."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-02'")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-02'")
    conn.commit()
    # Deliberately no row in sprint_metrics.sprints for 2024-02.

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # Establish the story's start so the 30-minute session is delivery.
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle2",
                event_type="started",
                timestamp="2024-02-05T10:00:00Z",
                sprint="2024-02",
            ),
        )
        # 30 minutes of story session (delivery).
        _post_events(
            f"{base}/events",
            _session_event("idle2", "2024-02", "2024-02-05T10:00:00Z", "2024-02-05T10:30:00Z"),
        )
        # 15 minutes of card-less session. 30 + 15 = 45 session minutes.
        _post_events(
            f"{base}/events",
            _session_event(None, "2024-02", "2024-02-05T11:00:00Z", "2024-02-05T11:15:00Z"),
        )
        status, body = _get_json(f"{base}/range?start=2024-02&end=2024-02")
        assert status == 200
        entry = body["sprints"]["2024-02"]
        assert entry["idle"] is None
        # The working-time answer still reads from the session records.
        assert entry["working_time"]["total"] == 45
    finally:
        conn.close()


@requires_db
def test_range_idle_null_when_no_session_ran():
    """AC2: a registered sprint that holds only board events and no session
    records carries the idle answer null — not the span-based idle it read
    before this release, and not 0 — and the flat idle_minutes name reads null
    in that sprint's prior and delta (the span-window calculation no longer
    feeds the idle answer)."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-03', '2024-04')")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-03', '2024-04')")
    conn.commit()
    _register_sprint(conn, "2024-03", "2024-03-01", "2024-03-14")
    _register_sprint(conn, "2024-04", "2024-04-01", "2024-04-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # Board events only — cards that started but never closed, no sessions.
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle3",
                event_type="started",
                timestamp="2024-03-05T10:00:00Z",
                sprint="2024-03",
            ),
        )
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle3b",
                event_type="started",
                timestamp="2024-04-05T10:00:00Z",
                sprint="2024-04",
            ),
        )
        status, body = _get_json(f"{base}/range?start=2024-03&end=2024-04")
        assert status == 200
        first = body["sprints"]["2024-03"]
        second = body["sprints"]["2024-04"]
        assert first["idle"] is None
        assert second["idle"] is None
        assert first["prior"] is None
        assert first["delta"] is None
        # The flat idle_minutes name reads null in the second sprint's prior and
        # delta (no span-based idle, no zero).
        assert second["prior"]["idle_minutes"] is None
        assert second["delta"]["idle_minutes"] is None
        # The working-time answer reads null too (no session records).
        assert first["working_time"] is None
        assert second["working_time"] is None
    finally:
        conn.close()


@requires_db
def test_range_idle_prior_and_delta_carry_idle_minutes():
    """AC4: a registered sprint carrying session records, followed by a sprint
    carrying none — the flat idle_minutes name keeps its shape in prior and
    delta: the value the first sprint carries on the second's prior, and null
    on the second's delta (the second carries no session records)."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-05', '2024-06')")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-05', '2024-06')")
    conn.commit()
    _register_sprint(conn, "2024-05", "2024-05-01", "2024-05-14")
    _register_sprint(conn, "2024-06", "2024-06-01", "2024-06-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-05: a 30-minute session -> idle 20130.
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle4a",
                event_type="started",
                timestamp="2024-05-05T10:00:00Z",
                sprint="2024-05",
            ),
        )
        _post_events(
            f"{base}/events",
            _session_event("idle4a", "2024-05", "2024-05-05T10:00:00Z", "2024-05-05T10:30:00Z"),
        )
        # 2024-06: only a board event, no session records -> idle null.
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle4b",
                event_type="started",
                timestamp="2024-06-05T10:00:00Z",
                sprint="2024-06",
            ),
        )
        status, body = _get_json(f"{base}/range?start=2024-05&end=2024-06")
        assert status == 200
        first = body["sprints"]["2024-05"]
        second = body["sprints"]["2024-06"]
        assert first["idle"]["idle_minutes"] == 20130
        assert first["prior"] is None
        assert first["delta"] is None
        assert second["idle"] is None
        assert second["prior"]["idle_minutes"] == 20130
        assert second["delta"]["idle_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_trend_idle_minutes():
    """AC4: GET /trend for the idle-time measure returns each sprint's idle
    minutes — the first sprint's value equals its /range idle time — and reads
    null for the sprint carrying no session records."""
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-07', '2024-08')")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-07', '2024-08')")
    conn.commit()
    _register_sprint(conn, "2024-07", "2024-07-01", "2024-07-14")
    _register_sprint(conn, "2024-08", "2024-08-01", "2024-08-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-07: a 30-minute session -> idle 20130.
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle5",
                event_type="started",
                timestamp="2024-07-05T10:00:00Z",
                sprint="2024-07",
            ),
        )
        _post_events(
            f"{base}/events",
            _session_event("idle5", "2024-07", "2024-07-05T10:00:00Z", "2024-07-05T10:30:00Z"),
        )
        # 2024-08: a board event only, no session records -> idle null.
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="idle5",
                event_type="started",
                timestamp="2024-08-05T10:00:00Z",
                sprint="2024-08",
            ),
        )
        status, body = _get_json(f"{base}/trend?start=2024-07&end=2024-08&metric=idle_minutes")
        assert status == 200
        assert body["metric"] == "idle_minutes"
        assert body["values"] == [
            {"sprint": "2024-07", "value": 20130},
            {"sprint": "2024-08", "value": None},
        ]
        # The first sprint's trend value equals its /range idle time.
        status, range_body = _get_json(f"{base}/range?start=2024-07&end=2024-07")
        assert status == 200
        assert range_body["sprints"]["2024-07"]["idle"]["idle_minutes"] == 20130
    finally:
        conn.close()


def test_range_schema_declares_idle_on_sprint_entry():
    """AC5: SPRINT_RANGE_SCHEMA declares idle as an optional property per sprint
    entry (not in required), with sprint_duration_minutes (integer) and
    idle_minutes (integer — the sprint's registered span minus its session
    minutes, never null once the object is present; null is carried by the
    object itself), and the flat idle_minutes name on prior and delta."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "idle" not in sprint_entry["required"]
    idle = sprint_entry["properties"]["idle"]
    assert idle["type"] == ["object", "null"]
    assert idle["required"] == ["sprint_duration_minutes", "idle_minutes"]
    assert idle["properties"]["sprint_duration_minutes"] == {"type": "integer"}
    assert idle["properties"]["idle_minutes"] == {"type": "integer"}
    # The flat name appears in prior and delta.
    prior = sprint_entry["properties"]["prior"]["properties"]
    assert prior["idle_minutes"] == {"type": ["integer", "null"]}
    delta = sprint_entry["properties"]["delta"]["properties"]
    assert delta["idle_minutes"] == {"type": ["integer", "null"]}
