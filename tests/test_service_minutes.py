"""Service tests for card.created_at and the cycle and lead times in minutes."""

from __future__ import annotations

from datetime import UTC

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
def test_post_event_with_created_at_stores_timestamp():
    """AC1+AC5: POST /events with card.created_at stores the timestamp in card_created_at."""
    from datetime import datetime

    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_subday'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c_subday",
            "type": "started",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-10", "created_at": "2024-01-10T08:30:00Z", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT card_created_at FROM sprint_metrics.board_events "
            "WHERE card_id = 'c_subday' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        expected = datetime(2024, 1, 10, 8, 30, 0, tzinfo=UTC)
        assert rows[0][0] == expected
    finally:
        conn.close()


@requires_db
def test_post_event_without_created_at_stores_null():
    """AC2+AC6: POST /events without card.created_at stores NULL in card_created_at."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_no_created_at'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c_no_created_at",
            "type": "started",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-10"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT card_created_at FROM sprint_metrics.board_events "
            "WHERE card_id = 'c_no_created_at' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        conn.close()


@requires_db
def test_post_event_with_invalid_created_at_returns_400():
    """AC3: POST /events with unparseable card.created_at returns 400 with error."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_bad_ts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c_bad_ts",
            "type": "started",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-10", "created_at": "not-a-timestamp"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str)
        assert len(body["error"]) > 0
    finally:
        conn.close()


@requires_db
def test_sprint_cycle_and_lead_time_minutes_sub_day():
    """AC1: sub-day cycle and lead time returned as integer minutes via /sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_subday'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_subday",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_subday",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["cycle_time_minutes"] == 686
        assert sprint_data["cycle_time_days"] == 0
        assert sprint_data["lead_time_minutes"] == 3686
        assert sprint_data["lead_time_days"] == 2
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_minute_fields_null():
    """AC2: /range with no stored events returns cycle_time_minutes and lead_time_minutes as null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        sprint_data = body["sprints"]["2024-03"]
        assert sprint_data["cycle_time_minutes"] is None
        assert sprint_data["lead_time_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_cycle_and_lead_time_minutes_prior_and_delta():
    """AC3+AC4: /range returns cycle_time_minutes for populated sprint, null for gap sprint,
    prior carries the populated value, and delta is null for the gap sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_range_min'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_min",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_min",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2024-01"]["cycle_time_minutes"] == 686
        assert sprints["2024-01"]["lead_time_minutes"] == 3686
        assert sprints["2024-02"]["cycle_time_minutes"] is None
        assert sprints["2024-02"]["lead_time_minutes"] is None
        assert sprints["2024-02"]["prior"]["cycle_time_minutes"] == 686
        assert sprints["2024-02"]["prior"]["lead_time_minutes"] == 3686
        assert sprints["2024-02"]["delta"]["cycle_time_minutes"] is None
        assert sprints["2024-02"]["delta"]["lead_time_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_same_day_card_minute_fields():
    """AC5: same-day card returns cycle_time_days=0, lead_time_days=0,
    cycle_time_minutes=30, lead_time_minutes=90 coexisting in the same response."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_sameday'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_sameday",
                event_type="started",
                timestamp="2024-01-03T09:00:00Z",
                sprint="2024-01",
                created="2024-01-03",
                created_at="2024-01-03T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_sameday",
                event_type="finished",
                timestamp="2024-01-03T09:30:00Z",
                sprint="2024-01",
                created="2024-01-03",
                created_at="2024-01-03T08:00:00Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["cycle_time_days"] == 0
        assert sprint_data["lead_time_days"] == 0
        assert sprint_data["cycle_time_minutes"] == 30
        assert sprint_data["lead_time_minutes"] == 90
    finally:
        conn.close()


@requires_db
def test_sprint_cycle_and_lead_time_minutes_rounding():
    """AC10: sub-day spans rounded to whole minutes: 685.87→686, 877.6→878."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac10_round'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac10_round",
                event_type="started",
                timestamp="2026-10-11T07:31:56Z",
                sprint="2026-10",
                created="2026-10-11",
                created_at="2026-10-11T04:20:12Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac10_round",
                event_type="finished",
                timestamp="2026-10-11T18:57:48Z",
                sprint="2026-10",
                created="2026-10-11",
                created_at="2026-10-11T04:20:12Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        sprint_data = body["sprints"]["2026-10"]
        assert sprint_data["cycle_time_minutes"] == 686
        assert sprint_data["lead_time_minutes"] == 878
    finally:
        conn.close()


@requires_db
def test_trend_cycle_time_minutes_two_sprints():
    """AC1/UX4: GET /trend?metric=cycle_time_minutes returns 200 with integer values.

    Sprint 2024-01: started 10:00, finished 21:26 → 686 minutes.
    Sprint 2024-02: started 08:00, finished 10:30 → 150 minutes.
    """
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac_ctm_a', 'ac_ctm_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-03",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_a",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-03",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_b",
                event_type="started",
                timestamp="2024-02-05T08:00:00Z",
                sprint="2024-02",
                created="2024-02-05",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_b",
                event_type="finished",
                timestamp="2024-02-05T10:30:00Z",
                sprint="2024-02",
                created="2024-02-05",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_minutes&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["metric"] == "cycle_time_minutes"
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 686}
        assert body["values"][1] == {"sprint": "2024-02", "value": 150}
        assert isinstance(body["values"][0]["value"], int)
        assert isinstance(body["values"][1]["value"], int)
    finally:
        conn.close()


@requires_db
def test_trend_lead_time_minutes_gap_sprint_null():
    """AC2/UX5: GET /trend?metric=lead_time_minutes over three sprints where the
    middle sprint has no events: that sprint's value is JSON null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac_ltm_a', 'ac_ltm_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created_at 2024-01-01T08:00:00Z, finished 2024-01-03T21:26:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_a",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        # Sprint 2024-03: created_at 2024-03-01T08:00:00Z, finished 2024-03-03T10:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_b",
                event_type="started",
                timestamp="2024-03-03T09:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
                created_at="2024-03-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_b",
                event_type="finished",
                timestamp="2024-03-03T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
                created_at="2024-03-01T08:00:00Z",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=lead_time_minutes&start=2024-01&end=2024-03"
        )
        assert status == 200
        assert len(body["values"]) == 3
        assert body["values"][0]["sprint"] == "2024-01"
        assert isinstance(body["values"][0]["value"], int)
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert "value" in body["values"][1]
        assert body["values"][1]["value"] is None
        assert body["values"][2]["sprint"] == "2024-03"
        assert isinstance(body["values"][2]["value"], int)
    finally:
        conn.close()


@requires_db
def test_trend_lead_time_minutes_single_sprint_integer():
    """UX7: GET /trend?metric=lead_time_minutes&start=2024-01&end=2024-01 (single
    sprint) returns 200 with one entry whose value is a JSON integer."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac_ltm_single'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_single",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_single",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=lead_time_minutes&start=2024-01&end=2024-01"
        )
        assert status == 200
        assert len(body["values"]) == 1
        assert body["values"][0]["sprint"] == "2024-01"
        assert isinstance(body["values"][0]["value"], int)
    finally:
        conn.close()
