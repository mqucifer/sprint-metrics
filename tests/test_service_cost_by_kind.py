"""Service tests for the cost_by_kind answer on /range and its two measures on /trend."""

from __future__ import annotations

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
def test_range_cost_by_kind_addition_and_change():
    """AC1: a sprint in which an addition-kind story carries 300 minutes of
    session time and a change-kind story carries 600 minutes has its
    cost_by_kind answer carry addition 300 and change 600 minutes."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cbk1', 'cbk2')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # addition-kind story: 300 min session
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbk1", event_type="started", timestamp="2024-01-02T09:00:00Z", sprint="2024-01", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbk1", event_type="finished", timestamp="2024-01-02T14:00:00Z", sprint="2024-01", kind="addition"),
        )
        # change-kind story: 600 min session
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbk2", event_type="started", timestamp="2024-01-03T08:00:00Z", sprint="2024-01", kind="change"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbk2", event_type="finished", timestamp="2024-01-03T18:00:00Z", sprint="2024-01", kind="change"),
        )
        status, body = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        assert status == 200
        entry = body["sprints"]["2024-01"]
        assert entry["cost_by_kind"] == {"addition": 300, "change": 600}
    finally:
        conn.close()


@requires_db
def test_range_cost_by_kind_null_when_no_kind():
    """AC2: a sprint whose stored story rows carry no story kind has its
    cost_by_kind answer null (no data, not zero; no backfill)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cbkn')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-02'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # story with no kind
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkn", event_type="started", timestamp="2024-02-02T09:00:00Z", sprint="2024-02"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkn", event_type="finished", timestamp="2024-02-02T10:00:00Z", sprint="2024-02"),
        )
        status, body = _get_json(f"{base}/range?start=2024-02&end=2024-02")
        assert status == 200
        entry = body["sprints"]["2024-02"]
        assert entry["cost_by_kind"] is None
    finally:
        conn.close()


@requires_db
def test_range_cost_by_kind_all_addition_zero_change():
    """AC3: a sprint in which every story carries kind 'addition' has its
    cost_by_kind answer carry the addition minutes and 0 for change (zero
    means 'no stories of that kind in this sprint', distinct from null)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cbka')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # one addition-kind story: 120 min
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbka", event_type="started", timestamp="2024-03-02T09:00:00Z", sprint="2024-03", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbka", event_type="finished", timestamp="2024-03-02T11:00:00Z", sprint="2024-03", kind="addition"),
        )
        status, body = _get_json(f"{base}/range?start=2024-03&end=2024-03")
        assert status == 200
        entry = body["sprints"]["2024-03"]
        assert entry["cost_by_kind"] == {"addition": 120, "change": 0}
    finally:
        conn.close()


@requires_db
def test_range_cost_by_kind_unknown_kind_contributes_to_neither():
    """AC4: a story whose kind is neither addition nor change contributes its
    minutes to neither kind."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cbku', 'cbkx')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-04'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # story with kind 'bug' (neither addition nor change): 60 min
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbku", event_type="started", timestamp="2024-04-02T09:00:00Z", sprint="2024-04", kind="bug"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbku", event_type="finished", timestamp="2024-04-02T10:00:00Z", sprint="2024-04", kind="bug"),
        )
        # story with kind 'addition': 30 min
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkx", event_type="started", timestamp="2024-04-03T09:00:00Z", sprint="2024-04", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkx", event_type="finished", timestamp="2024-04-03T09:30:00Z", sprint="2024-04", kind="addition"),
        )
        status, body = _get_json(f"{base}/range?start=2024-04&end=2024-04")
        assert status == 200
        entry = body["sprints"]["2024-04"]
        # The bug-kind story's 60 min contribute to neither; only the addition
        # story's 30 min count.
        assert entry["cost_by_kind"] == {"addition": 30, "change": 0}
    finally:
        conn.close()


@requires_db
def test_trend_addition_and_change_working_time():
    """AC5: GET /trend?metric=addition_working_time_minutes and
    change_working_time_minutes return the per-sprint whole minutes (null where
    the sprint carries no kind data)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cblk1', 'cblk2')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-05', '2024-06')")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-05: addition story 90 min, change story 60 min
        _post_events(
            f"{base}/events",
            _make_event(card_id="cblk1", event_type="started", timestamp="2024-05-02T09:00:00Z", sprint="2024-05", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cblk1", event_type="finished", timestamp="2024-05-02T10:30:00Z", sprint="2024-05", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cblk2", event_type="started", timestamp="2024-05-02T09:00:00Z", sprint="2024-05", kind="change"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cblk2", event_type="finished", timestamp="2024-05-02T10:00:00Z", sprint="2024-05", kind="change"),
        )
        # 2024-06: no events (no kind data)

        status, body = _get_json(
            f"{base}/trend?metric=addition_working_time_minutes&start=2024-05&end=2024-06"
        )
        assert status == 200
        assert body["metric"] == "addition_working_time_minutes"
        assert body["values"] == [
            {"sprint": "2024-05", "value": 90},
            {"sprint": "2024-06", "value": None},
        ]

        status, body = _get_json(
            f"{base}/trend?metric=change_working_time_minutes&start=2024-05&end=2024-06"
        )
        assert status == 200
        assert body["metric"] == "change_working_time_minutes"
        assert body["values"] == [
            {"sprint": "2024-05", "value": 60},
            {"sprint": "2024-06", "value": None},
        ]
    finally:
        conn.close()


@requires_db
def test_range_cost_by_kind_prior_and_delta():
    """AC6: the flat kind names appear in each later entry's prior and delta
    (null where a sprint has no kind data)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cbkp1', 'cbkp2')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-07', '2024-08')")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        # 2024-07: addition 60 min, change 30 min
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkp1", event_type="started", timestamp="2024-07-02T09:00:00Z", sprint="2024-07", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkp1", event_type="finished", timestamp="2024-07-02T10:00:00Z", sprint="2024-07", kind="addition"),
        )
        # 2024-08: addition 120 min, change 60 min
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkp2", event_type="started", timestamp="2024-08-02T09:00:00Z", sprint="2024-08", kind="addition"),
        )
        _post_events(
            f"{base}/events",
            _make_event(card_id="cbkp2", event_type="finished", timestamp="2024-08-02T11:00:00Z", sprint="2024-08", kind="addition"),
        )
        status, body = _get_json(f"{base}/range?start=2024-07&end=2024-08")
        assert status == 200
        e1 = body["sprints"]["2024-07"]
        e2 = body["sprints"]["2024-08"]
        assert e1["cost_by_kind"] == {"addition": 60, "change": 0}
        assert e2["cost_by_kind"] == {"addition": 120, "change": 0}
        assert e1["prior"] is None
        assert e1["delta"] is None
        assert e2["prior"]["addition_working_time_minutes"] == 60
        assert e2["prior"]["change_working_time_minutes"] == 0
        assert e2["delta"]["addition_working_time_minutes"] == 60
        assert e2["delta"]["change_working_time_minutes"] == 0
    finally:
        conn.close()


def test_sprint_range_schema_declares_cost_by_kind_on_sprint_entry():
    """AC6: SPRINT_RANGE_SCHEMA declares cost_by_kind as an optional property
    per sprint entry (not in required), with addition and change (integer)."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "cost_by_kind" not in sprint_entry["required"]
    cbk = sprint_entry["properties"]["cost_by_kind"]
    assert cbk["type"] == ["object", "null"]
    assert cbk["required"] == ["addition", "change"]
    assert cbk["properties"]["addition"] == {"type": "integer"}
    assert cbk["properties"]["change"] == {"type": "integer"}
