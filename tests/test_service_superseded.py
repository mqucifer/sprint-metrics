"""Service tests for the superseded event and the superseded measures."""

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

from sprint_metrics.report import API_VERSION
from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


@requires_db
def test_post_superseded_stores_full_metadata():
    """AC1: POST /events with type='superseded' stores because, epic, and replaced_by."""
    import json as json_mod

    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c9'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c9",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
            "epic": "Fix auth flow",
            "replaced_by": [480, 481],
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT because, epic, replaced_by FROM sprint_metrics.board_events "
            "WHERE card_id = 'c9' AND type = 'superseded'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "sponsor"
        assert rows[0][1] == "Fix auth flow"
        replaced = rows[0][2]
        if isinstance(replaced, str):
            replaced = json_mod.loads(replaced)
        assert replaced == [480, 481]
    finally:
        conn.close()


@requires_db
def test_post_superseded_invalid_because_returns_400():
    """AC3: POST /events with type='superseded' and because='invalid_reason' returns 400
    with an error naming the invalid value."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c9",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "invalid_reason",
            "epic": "Fix auth flow",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "invalid_reason" in body["error"]
    finally:
        conn.close()


@requires_db
def test_post_superseded_without_replaced_by_stores_null():
    """AC1: POST /events with type='superseded' and no replaced_by field returns 200,
    no error key, and the stored row has replaced_by column NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c10",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "story_problem",
            "epic": "Fix auth flow",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT replaced_by FROM sprint_metrics.board_events "
            "WHERE card_id = 'c10' AND type = 'superseded'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        conn.close()


@requires_db
def test_post_superseded_replaced_by_not_array_returns_400():
    """AC3: POST /events with type='superseded' and replaced_by='not_an_array' (a string)
    returns 400 with a non-empty error string."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c12",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "sponsor",
            "epic": "Fix auth flow",
            "replaced_by": "not_an_array",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str) and len(body["error"]) > 0
    finally:
        conn.close()


@requires_db
def test_post_superseded_no_prior_events_returns_200():
    """AC2: POST /events with type='superseded' for a card with no prior events
    returns 200 and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c11",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "sponsor",
            "epic": "Fix auth flow",
            "replaced_by": [500],
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_sprint_superseded_metrics_with_mixed_events():
    """AC1: GET /range returns superseded_count, superseded_points,
    superseded_breakdown from stored superseded events; superseded card
    excluded from throughput."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('sup_c1', 'sup_c2')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="sup_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-02",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "sup_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-02", "points": 5},
            "because": "sponsor",
        }
        finished_c2 = _make_event(
            card_id="sup_c2",
            event_type="finished",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            started="2024-01-02",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c2)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["superseded_count"] == 1
        assert sprint_data["superseded_points"] == 5
        assert sprint_data["superseded_breakdown"] == {"sponsor": 1, "story_problem": 0}
        assert sprint_data["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_range_superseded_metrics_per_sprint():
    """AC3: GET /range returns per-sprint superseded_count and superseded_points."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('rng_c1', 'rng_c2')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="rng_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "rng_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
        }
        started_c2 = _make_event(
            card_id="rng_c2",
            event_type="started",
            timestamp="2024-02-03T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        finished_c2 = _make_event(
            card_id="rng_c2",
            event_type="finished",
            timestamp="2024-02-07T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
            started="2024-02-02",
            points=3,
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", started_c2)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2024-01"]["superseded_count"] == 1
        assert sprints["2024-01"]["superseded_points"] == 5
        assert sprints["2024-02"]["superseded_count"] == 0
        assert sprints["2024-02"]["superseded_points"] == 0
    finally:
        conn.close()


@requires_db
def test_range_superseded_prior_and_delta():
    """AC4: GET /range prior and delta include superseded_count and superseded_points."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('rngd_c1', 'rngd_c2')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="rngd_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "rngd_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
        }
        started_c2 = _make_event(
            card_id="rngd_c2",
            event_type="started",
            timestamp="2024-02-03T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        finished_c2 = _make_event(
            card_id="rngd_c2",
            event_type="finished",
            timestamp="2024-02-07T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
            started="2024-02-02",
            points=3,
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", started_c2)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2024-02"]["prior"]["superseded_count"] == 1
        assert sprints["2024-02"]["prior"]["superseded_points"] == 5
        assert sprints["2024-02"]["delta"]["superseded_count"] == -1
        assert sprints["2024-02"]["delta"]["superseded_points"] == -5
    finally:
        conn.close()


@requires_db
def test_sprint_superseded_excluded_from_throughput():
    """AC5: A superseded card is not counted as delivered; throughput is 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'supt_c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="supt_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-02",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "supt_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-02", "points": 5},
            "because": "sponsor",
        }
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["throughput"] == 0
        assert body["sprints"]["2024-01"]["superseded_count"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_multiple_superseded_breakdown():
    """AC7: Two superseded cards (sponsor, story_problem) plus one finished card
    produce superseded_count=2, superseded_points=8, correct breakdown, throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('sup2_c1', 'sup2_c2', 'sup2_c3')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        superseded_c1 = {
            "api_version": "1",
            "card_id": "sup2_c1",
            "type": "superseded",
            "timestamp": "2024-01-03T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
        }
        superseded_c2 = {
            "api_version": "1",
            "card_id": "sup2_c2",
            "type": "superseded",
            "timestamp": "2024-01-03T11:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 3},
            "because": "story_problem",
        }
        finished_c3 = _make_event(
            card_id="sup2_c3",
            event_type="finished",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            started="2024-01-02",
        )
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c2)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c3)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01", timeout=5
        ) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Type", "") == "application/json"
            body = json.loads(resp.read().decode())

        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["superseded_count"] == 2
        assert sprint_data["superseded_points"] == 8
        assert sprint_data["superseded_breakdown"] == {"sponsor": 1, "story_problem": 1}
        assert sprint_data["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_only_started_superseded_zeros_not_null():
    """AC8: A sprint with only a started event (no superseded, no finished)
    returns integer zeros for superseded fields, not null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'zero_c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="zero_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["superseded_count"] == 0
        assert sprint_data["superseded_points"] == 0
        assert sprint_data["superseded_breakdown"] == {"sponsor": 0, "story_problem": 0}
        assert sprint_data["throughput"] == 0
        assert isinstance(sprint_data["superseded_count"], int)
        assert isinstance(sprint_data["superseded_points"], int)
        assert isinstance(sprint_data["superseded_breakdown"], dict)
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_superseded_fields_null():
    """AC2: A sprint with no events returns null for superseded_count,
    superseded_points, and superseded_breakdown."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-11&end=2026-11")
        assert status == 200
        sprint_data = body["sprints"]["2026-11"]
        assert sprint_data["superseded_count"] is None
        assert sprint_data["superseded_points"] is None
        assert sprint_data["superseded_breakdown"] is None
    finally:
        conn.close()


@requires_db
def test_trend_superseded_count_three_sprints():
    """AC1: GET /trend?metric=superseded_count&start=2024-01&end=2024-03 with
    a superseded event for card c1 in sprint 2024-01 (because "sponsor", points 5)
    and a superseded event for card c2 in sprint 2024-02 (because "story_problem",
    points 3) returns 200, Content-Type application/json, and values array has
    exactly three entries in order: 2024-01 value 1, 2024-02 value 1, 2024-03 value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_sup_c1', 'ac1_sup_c2')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02', '2024-03')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: superseded event for card c1 (because "sponsor", points 5)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac1_sup_c1",
                "type": "superseded",
                "sprint": "2024-01",
                "timestamp": "2024-01-15T10:00:00Z",
                "card": {"created": "2024-01-01", "points": 5},
                "because": "sponsor",
            },
        )
        # Sprint 2024-02: superseded event for card c2 (because "story_problem", points 3)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac1_sup_c2",
                "type": "superseded",
                "sprint": "2024-02",
                "timestamp": "2024-02-15T10:00:00Z",
                "card": {"created": "2024-02-01", "points": 3},
                "because": "story_problem",
            },
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=superseded_count&start=2024-01&end=2024-03",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == API_VERSION
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-01", "value": 1}
        assert body["values"][1] == {"sprint": "2024-02", "value": 1}
        assert body["values"][2] == {"sprint": "2024-03", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_points_two_sprints():
    """AC2: GET /trend?metric=superseded_points&start=2024-01&end=2024-02 with
    a superseded event for card c1 in sprint 2024-01 (points 5) and card c2 in
    sprint 2024-02 (points 3) returns 200 with values array having two entries:
    2024-01 value 5 and 2024-02 value 3."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac2_sup_c1', 'ac2_sup_c2')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac2_sup_c1",
                "type": "superseded",
                "sprint": "2024-01",
                "timestamp": "2024-01-15T10:00:00Z",
                "card": {"created": "2024-01-01", "points": 5},
                "because": "sponsor",
            },
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac2_sup_c2",
                "type": "superseded",
                "sprint": "2024-02",
                "timestamp": "2024-02-15T10:00:00Z",
                "card": {"created": "2024-02-01", "points": 3},
                "because": "story_problem",
            },
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=superseded_points&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 5}
        assert body["values"][1] == {"sprint": "2024-02", "value": 3}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_count_empty_db_returns_nulls():
    """AC4: GET /trend?metric=superseded_count&start=2024-01&end=2024-02 on an
    empty DB returns 200 with values array having two entries both with value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=superseded_count&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_count_four_sprints_with_gap():
    """AC6 (UX): GET /trend?metric=superseded_count&start=2024-01&end=2024-04 with
    events in 2024-01 and 2024-03 but not 2024-02 or 2024-04 returns 200,
    Content-Type application/json, and values array has exactly four entries in
    order: 2024-01 value 1, 2024-02 value null, 2024-03 value 1, 2024-04 value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_sup_c1', 'ac6_sup_c2')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN "
        "('2024-01', '2024-02', '2024-03', '2024-04')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: superseded event for card c1
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac6_sup_c1",
                "type": "superseded",
                "sprint": "2024-01",
                "timestamp": "2024-01-15T10:00:00Z",
                "card": {"created": "2024-01-01", "points": 5},
                "because": "sponsor",
            },
        )
        # Sprint 2024-03: superseded event for card c2
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac6_sup_c2",
                "type": "superseded",
                "sprint": "2024-03",
                "timestamp": "2024-03-15T10:00:00Z",
                "card": {"created": "2024-03-01", "points": 3},
                "because": "story_problem",
            },
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=superseded_count&start=2024-01&end=2024-04",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 4
        assert body["values"][0] == {"sprint": "2024-01", "value": 1}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert body["values"][2] == {"sprint": "2024-03", "value": 1}
        assert body["values"][3] == {"sprint": "2024-04", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_points_empty_db_returns_nulls():
    """AC7 (UX): GET /trend?metric=superseded_points&start=2024-01&end=2024-02 on
    an empty DB returns 200 with values array having exactly two entries both
    with value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=superseded_points&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
    finally:
        conn.close()
