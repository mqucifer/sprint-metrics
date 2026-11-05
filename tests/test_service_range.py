"""Service tests for GET /range: its entries, prior and delta, sprint order, and named sprints."""

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
from sprint_metrics.verdict import MEASURE_REGISTRY


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
        assert body["api_version"] == API_VERSION
        assert body["window"]["start"] == "2024-01"
        assert body["window"]["end"] == "2024-02"
        assert body["window"]["sprint_count"] == 2
        assert body["window"]["no_data"] == []
        assert set(body["window"]["verdicts"]) == set(MEASURE_REGISTRY)
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
            f"http://127.0.0.1:{port}/range?start=2024-05&end=2024-05", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["sprints"]["2024-05"]["throughput"] == 0
        assert body["sprints"]["2024-05"]["cycle_time_days"] == 0
        assert body["sprints"]["2024-05"]["lead_time_days"] == 0
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
            f"http://127.0.0.1:{port}/range?start=2026-11&end=2026-11", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        sprint_data = body["sprints"]["2026-11"]
        assert sprint_data["throughput"] is None
        assert sprint_data["cycle_time_days"] is None
        assert sprint_data["lead_time_days"] is None
        assert sprint_data["failure_breakdown"] is None
        assert sprint_data["top_failure_causes"] is None
        assert sprint_data["flags"] is None
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

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        sprint_data = body["sprints"]["2026-10"]
        assert sprint_data["throughput"] == 1
        assert sprint_data["cycle_time_days"] == 0
        assert isinstance(sprint_data["failure_breakdown"], list)
        assert len(sprint_data["failure_breakdown"]) == 1
        assert sprint_data["first_attempt_rate_percent"] == 0
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
        assert sprints["2026-11"]["cycle_time_minutes"] is None
        assert sprints["2026-11"]["lead_time_minutes"] is None
        assert sprints["2026-12"]["cycle_time_minutes"] is None
        assert sprints["2026-12"]["lead_time_minutes"] is None
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
def test_range_single_named_sprint_registered_returns_200():
    """AC1: GET /range?start=Sprint%206&end=Sprint%206 with Sprint 6 registered
    returns 200 and the sprints object has exactly one key, 'Sprint 6'."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 6'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = 'Sprint 6'")
    conn.commit()

    upsert_sprint(conn, "Sprint 6", date(2024, 3, 4), date(2024, 3, 15), "UTC")

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_named_single",
                event_type="started",
                timestamp="2024-03-05T10:00:00Z",
                sprint="Sprint 6",
                created="2024-03-04",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_named_single",
                event_type="finished",
                timestamp="2024-03-08T15:00:00Z",
                sprint="Sprint 6",
                created="2024-03-04",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=Sprint%206&end=Sprint%206")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["Sprint 6"]
    finally:
        conn.close()


@requires_db
def test_range_single_named_sprint_unregistered_returns_400():
    """AC2: GET /range?start=Sprint%206&end=Sprint%206 with Sprint 6 NOT registered
    returns 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 6'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = 'Sprint 6'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=Sprint%206&end=Sprint%206")
        assert status == 400
        assert "error" in body
    finally:
        conn.close()


class _FakeSprintCursor:
    """Minimal cursor that returns pre-loaded rows from fetchall."""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSprintConn:
    """In-memory stand-in for a psycopg connection, sufficient for
    store.resolve_sprint_range. No database or SPRINT_METRICS_DB required."""

    def __init__(self, sprints):
        self._sprints = sprints

    def execute(self, sql, params=()):
        if "start_date BETWEEN" in sql:
            lo, hi = params
            names = sorted(
                (name for name, sd in self._sprints.items() if lo <= sd <= hi),
                key=lambda name: (self._sprints[name], name),
            )
            rows = [(name,) for name in names]
        else:
            wanted = set(params)
            rows = [(name, sd) for name, sd in self._sprints.items() if name in wanted]
        return _FakeSprintCursor(rows)


def test_resolve_sprint_range_single_named_sprint_returns_that_sprint():
    """AC1: a range of one registered sprint (start == end) resolves to that
    sprint, not None. Fails against the old len(rows) < 2 guard that made a
    single-sprint range look unregistered."""
    from datetime import date

    from sprint_metrics.store import resolve_sprint_range

    conn = _FakeSprintConn({"Sprint 6": date(2024, 3, 4)})
    assert resolve_sprint_range(conn, "Sprint 6", "Sprint 6") == ["Sprint 6"]


def test_resolve_sprint_range_single_unregistered_sprint_returns_none():
    """AC2: a range of one non-registered name still resolves to None (the 400
    path), so the calendar-month fallback is reached rather than a silent
    single-sprint answer."""
    from sprint_metrics.store import resolve_sprint_range

    conn = _FakeSprintConn({})
    assert resolve_sprint_range(conn, "Sprint 6", "Sprint 6") is None
