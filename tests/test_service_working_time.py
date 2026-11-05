"""Service tests for the working_time answer on /range and working_time_minutes on /trend."""

from __future__ import annotations

from service_helpers import (
    SPRINT_METRICS_DB,
    _clean_board_events,  # noqa: F401 (autouse: empties the tables)
    _get_json,
    _make_event,
    _post_events,
    requires_db,
)

from sprint_metrics.report import API_VERSION
from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


@requires_db
def test_range_working_time_per_step_and_total():
    """AC1: a sprint whose stored session records are: story X 22 minutes and
    story Y 5 minutes (both from their stories' starts on), a planning session
    of 10 minutes (before its story's start), and a card-less session of 8
    minutes, all sent with the sprint's label — the sprint's working-time total
    reads 45 (22 + 5 + 10 + 8) in whole minutes, and the displayed story parts,
    the planning part and the card-less part sum exactly to the displayed sprint
    total."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-03'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # Story X: started at 09:00, session from 09:00 to 09:22 (22 min delivery)
        _post_events(
            f"{base}/events",
            _make_event(card_id="X", event_type="started", timestamp="2024-03-02T09:00:00Z", sprint="2024-03"),
        )
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "X",
                "type": "session",
                "timestamp": "2024-03-02T09:00:00Z",
                "sprint": "2024-03",
                "card": {"created": "2024-03-01"},
                "role": "developer",
                "start": "2024-03-02T09:00:00Z",
                "end": "2024-03-02T09:22:00Z",
            },
        )
        # Story Y: started at 09:00, session from 09:00 to 09:05 (5 min delivery)
        _post_events(
            f"{base}/events",
            _make_event(card_id="Y", event_type="started", timestamp="2024-03-03T09:00:00Z", sprint="2024-03"),
        )
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "Y",
                "type": "session",
                "timestamp": "2024-03-03T09:00:00Z",
                "sprint": "2024-03",
                "card": {"created": "2024-03-01"},
                "role": "developer",
                "start": "2024-03-03T09:00:00Z",
                "end": "2024-03-03T09:05:00Z",
            },
        )
        # Planning session for story X: 10 minutes before the story's start (08:00 -> 08:10)
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "X",
                "type": "session",
                "timestamp": "2024-03-02T08:00:00Z",
                "sprint": "2024-03",
                "card": {"created": "2024-03-01"},
                "role": "developer",
                "start": "2024-03-02T08:00:00Z",
                "end": "2024-03-02T08:10:00Z",
            },
        )
        # Card-less session: 8 minutes (14:00 -> 14:08)
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "type": "session",
                "timestamp": "2024-03-02T14:00:00Z",
                "sprint": "2024-03",
                "role": "developer",
                "start": "2024-03-02T14:00:00Z",
                "end": "2024-03-02T14:08:00Z",
            },
        )

        status, body = _get_json(f"{base}/range?start=2024-03&end=2024-03")
        assert status == 200
        wt = body["sprints"]["2024-03"]["working_time"]
        assert wt is not None
        assert wt["stories"] == {"X": 22, "Y": 5}
        assert wt["planning"] == 10
        assert wt["cardless"] == 8
        assert wt["total"] == 45
        # displayed parts sum to the total
        assert sum(wt["stories"].values()) + wt["planning"] + wt["cardless"] == wt["total"]
    finally:
        conn.close()


@requires_db
def test_range_working_time_blocked_interval_not_counted():
    """AC2: a sprint that holds exactly one card-less session record (8 minutes)
    and no board events at all — the sprint's working time reads 8, with the
    card-less session as a named part of the total the reader can pick out, and
    the 8 minutes belong to no story — no story's session numbers are affected."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-04'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-04'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # Card-less session: 8 minutes (14:00 -> 14:08)
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "type": "session",
                "timestamp": "2024-04-02T14:00:00Z",
                "sprint": "2024-04",
                "role": "developer",
                "start": "2024-04-02T14:00:00Z",
                "end": "2024-04-02T14:08:00Z",
            },
        )
        status, body = _get_json(f"{base}/range?start=2024-04&end=2024-04")
        assert status == 200
        wt = body["sprints"]["2024-04"]["working_time"]
        assert wt is not None
        assert wt["stories"] == {}
        assert wt["planning"] == 0
        assert wt["cardless"] == 8
        assert wt["total"] == 8
    finally:
        conn.close()


@requires_db
def test_range_working_time_null_when_no_session_timestamps():
    """AC3: a sprint that holds only board events ('started' and 'finished' rows,
    including the old cost payload) and no session records at all — the
    working-time answer reads null — not the span-based minutes it read before
    this release, and not 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-05'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('wtns')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-05'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # Board events only, no session records
        _post_events(
            f"{base}/events",
            _make_event(card_id="wtns", event_type="started", timestamp="2024-05-02T09:00:00Z", sprint="2024-05"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="wtns", event_type="finished", timestamp="2024-05-02T11:00:00Z", sprint="2024-05"),
        )
        status, body = _get_json(f"{base}/range?start=2024-05&end=2024-05")
        assert status == 200
        entry = body["sprints"]["2024-05"]
        assert entry["working_time"] is None
    finally:
        conn.close()


@requires_db
def test_range_working_time_null_when_no_events():
    """AC3b: a sprint in the window with no events at all and no session records
    carries working_time null (not zero)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-06', '2024-07')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-06', '2024-07')")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        status, body = _get_json(f"{base}/range?start=2024-06&end=2024-07")
        assert status == 200
        assert body["sprints"]["2024-06"]["working_time"] is None
        assert body["sprints"]["2024-07"]["working_time"] is None
    finally:
        conn.close()


@requires_db
def test_range_working_time_prior_and_delta():
    """AC4: for every sprint after the first, the flat working_time_minutes name
    appears in that entry's prior and delta; a sprint with data in both carries a
    prior (the earlier sprint's total) and a signed delta."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-08', '2024-09')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('wtp1', 'wtp2')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-08', '2024-09')")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-08: story wtp1 with 60 minutes of delivery session time
        _post_events(
            f"{base}/events",
            _make_event(card_id="wtp1", event_type="started", timestamp="2024-08-02T09:00:00Z", sprint="2024-08"),
        )
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "wtp1",
                "type": "session",
                "timestamp": "2024-08-02T09:00:00Z",
                "sprint": "2024-08",
                "card": {"created": "2024-08-01"},
                "role": "developer",
                "start": "2024-08-02T09:00:00Z",
                "end": "2024-08-02T10:00:00Z",
            },
        )
        # 2024-09: story wtp2 with 120 minutes of delivery session time
        _post_events(
            f"{base}/events",
            _make_event(card_id="wtp2", event_type="started", timestamp="2024-09-02T09:00:00Z", sprint="2024-09"),
        )
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "wtp2",
                "type": "session",
                "timestamp": "2024-09-02T09:00:00Z",
                "sprint": "2024-09",
                "card": {"created": "2024-09-01"},
                "role": "developer",
                "start": "2024-09-02T09:00:00Z",
                "end": "2024-09-02T11:00:00Z",
            },
        )
        status, body = _get_json(f"{base}/range?start=2024-08&end=2024-09")
        assert status == 200
        e1 = body["sprints"]["2024-08"]
        e2 = body["sprints"]["2024-09"]
        assert e1["working_time"]["total"] == 60
        assert e2["working_time"]["total"] == 120
        assert e1["prior"] is None
        assert e1["delta"] is None
        assert e2["prior"]["working_time_minutes"] == 60
        assert e2["delta"]["working_time_minutes"] == 60
    finally:
        conn.close()


@requires_db
def test_range_working_time_null_prior_delta_when_prior_no_data():
    """AC4b: when the prior sprint has no session records (no working-time data),
    that entry's prior and delta carry working_time_minutes null, while the
    current sprint's own total is present."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-10', '2024-11')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('wtpd_a', 'wtpd_b')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-10', '2024-11')")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-10: board events but no session records (no working time data)
        _post_events(
            f"{base}/events",
            _make_event(card_id="wtpd_a", event_type="started", timestamp="2024-10-02T09:00:00Z", sprint="2024-10"),
        )
        # 2024-11: a 60-minute delivery session
        _post_events(
            f"{base}/events",
            _make_event(card_id="wtpd_b", event_type="started", timestamp="2024-11-02T09:00:00Z", sprint="2024-11"),
        )
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "wtpd_b",
                "type": "session",
                "timestamp": "2024-11-02T09:00:00Z",
                "sprint": "2024-11",
                "card": {"created": "2024-11-01"},
                "role": "developer",
                "start": "2024-11-02T09:00:00Z",
                "end": "2024-11-02T10:00:00Z",
            },
        )
        status, body = _get_json(f"{base}/range?start=2024-10&end=2024-11")
        assert status == 200
        e10 = body["sprints"]["2024-10"]
        e11 = body["sprints"]["2024-11"]
        assert e10["working_time"] is None
        assert e11["working_time"]["total"] == 60
        assert e11["prior"]["working_time_minutes"] is None
        assert e11["delta"]["working_time_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_trend_working_time_minutes():
    """AC6: GET /trend?metric=working_time_minutes returns the sprint's
    working-time total in whole minutes (null for a sprint with no session
    records)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-11', '2024-12')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('wttd')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-11', '2024-12')")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-11: a 150-minute delivery session
        _post_events(
            f"{base}/events",
            _make_event(card_id="wttd", event_type="started", timestamp="2024-11-02T09:00:00Z", sprint="2024-11"),
        )
        _post_events(
            f"{base}/events",
            {
                "api_version": "1",
                "card_id": "wttd",
                "type": "session",
                "timestamp": "2024-11-02T09:00:00Z",
                "sprint": "2024-11",
                "card": {"created": "2024-11-01"},
                "role": "developer",
                "start": "2024-11-02T09:00:00Z",
                "end": "2024-11-02T11:30:00Z",
            },
        )
        status, body = _get_json(f"{base}/trend?metric=working_time_minutes&start=2024-11&end=2024-12")
        assert status == 200
        assert body["api_version"] == API_VERSION
        assert body["metric"] == "working_time_minutes"
        assert body["values"] == [
            {"sprint": "2024-11", "value": 150},
            {"sprint": "2024-12", "value": None},
        ]
    finally:
        conn.close()


def test_sprint_range_schema_declares_working_time_on_sprint_entry():
    """AC7: SPRINT_RANGE_SCHEMA declares working_time as an optional property per
    sprint entry (not in required), with stories (object of integers), planning
    (integer), cardless (integer), and total (integer)."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "working_time" not in sprint_entry["required"]
    wt = sprint_entry["properties"]["working_time"]
    assert wt["type"] == ["object", "null"]
    assert wt["required"] == ["stories", "planning", "cardless", "total"]
    assert wt["properties"]["total"] == {"type": "integer"}
    assert wt["properties"]["stories"]["type"] == "object"
    assert wt["properties"]["stories"]["additionalProperties"] == {"type": "integer"}
    assert wt["properties"]["planning"] == {"type": "integer"}
    assert wt["properties"]["cardless"] == {"type": "integer"}
