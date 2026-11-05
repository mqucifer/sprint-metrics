"""Service tests for GET /trend: its values, gaps, order, refusals and response shape."""

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
def test_trend_cycle_time_three_sprints():
    """AC1: GET /trend?metric=cycle_time_days&start=2024-02&end=2024-04 returns
    200 with three entries: 2024-02 value 3, 2024-03 value null, 2024-04 value 6."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_trend_a', 'ac1_trend_b', 'ac1_trend_c', 'ac1_trend_d')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card, cycle 4 (created 01-01, started 01-02, finished 01-06)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: two cards, each cycle 3 (created 02-01, started 02-02, finished 02-05)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_b",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_c",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_c",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        # 2024-04: one card, cycle 6 (created 04-01, started 04-02, finished 04-08)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_d",
                event_type="started",
                timestamp="2024-04-02T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_d",
                event_type="finished",
                timestamp="2024-04-08T15:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-02&end=2024-04",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == API_VERSION
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-02", "value": 3}
        assert body["values"][1] == {"sprint": "2024-03", "value": None}
        assert body["values"][2] == {"sprint": "2024-04", "value": 6}
    finally:
        conn.close()


@requires_db
def test_trend_empty_db_all_zeros():
    """AC2: GET /trend?metric=throughput&start=2024-01&end=2024-03 on an empty DB
    returns 200 with three entries, all value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-03"
        )
        assert status == 200
        assert body["api_version"] == API_VERSION
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert body["values"][2] == {"sprint": "2024-03", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_invalid_metric_returns_400():
    """AC2: GET /trend?metric=bogus_metric&start=2024-01&end=2024-02 returns 400
    with error containing 'bogus_metric'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=bogus_metric&start=2024-01&end=2024-02"
        )
        assert status == 400
        assert "bogus_metric" in body["error"]
    finally:
        conn.close()


@requires_db
def test_trend_start_after_end_returns_400():
    """AC4: GET /trend?metric=throughput&start=2024-03&end=2024-01 returns 400
    with error naming both '2024-03' and '2024-01'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-03&end=2024-01"
        )
        assert status == 400
        assert "2024-03" in body["error"]
        assert "2024-01" in body["error"]
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_rate_two_sprints():
    """AC5: GET /trend?metric=first_attempt_rate_percent&start=2024-01&end=2024-02
    returns 200 with two entries: 2024-01 value 100 (one card, attempts=1),
    2024-02 value 0 (one card, attempts=2)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac5_trend_a', 'ac5_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one completed card, default attempts=1 → 100%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: one completed card, attempts=2 → 0%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_b",
                event_type="finished",
                timestamp="2024-02-07T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                attempts=2,
                failure_class="parse",
                failure_role="Developer",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_rate_percent"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["api_version"] == API_VERSION
        assert len(body["values"]) == 2
        assert body["values"][0]["sprint"] == "2024-01"
        assert body["values"][0]["value"] == 100
        assert body["values"][1]["sprint"] == "2024-02"
        assert body["values"][1]["value"] == 0
    finally:
        conn.close()


@requires_db
def test_trend_response_includes_metric_and_span_labels():
    """UX6: GET /trend?metric=cycle_time_days&start=2024-01&end=2024-02 response
    has top-level keys whose values are 'cycle_time_days', '2024-01', '2024-02'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_trend_a', 'ac6_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_b",
                event_type="started",
                timestamp="2024-02-01T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_b",
                event_type="finished",
                timestamp="2024-02-04T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-01&end=2024-02"
        )
        assert status == 200
        values = list(body.values())
        assert "cycle_time_days" in values
        assert "2024-01" in values
        assert "2024-02" in values
    finally:
        conn.close()


@requires_db
def test_trend_six_sprints_zero_fill_empty_sprint():
    """UX7: GET /trend?metric=throughput&start=2024-01&end=2024-06 with no events
    for 2024-03 returns six entries in order, 2024-03 has value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac7_trend_a', 'ac7_trend_b', 'ac7_trend_c', 'ac7_trend_d', 'ac7_trend_e')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Add one finished card to each of 2024-01, 02, 04, 05, 06 (not 03)
        sprints_with_data = ["2024-01", "2024-02", "2024-04", "2024-05", "2024-06"]
        for i, sprint in enumerate(sprints_with_data):
            card_id = f"ac7_trend_{chr(ord('a') + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp=f"{sprint}-03T10:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp=f"{sprint}-07T15:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-06"
        )
        assert status == 200
        assert len(body["values"]) == 6
        expected_order = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
        for entry, label in zip(body["values"], expected_order, strict=True):
            assert entry["sprint"] == label
        assert body["values"][2]["value"] is None
        assert body["values"][0]["value"] == 1
        assert body["values"][1]["value"] == 1
        assert body["values"][3]["value"] == 1
        assert body["values"][4]["value"] == 1
        assert body["values"][5]["value"] == 1
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_rate_integer_not_string_or_float():
    """UX8: GET /trend?metric=first_attempt_rate_percent with 2024-01 attempts=2
    (value 0) and 2024-02 attempts=1 (value 100) returns JSON integers."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac8_trend_a', 'ac8_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card with attempts=2 → 0%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=2,
                failure_class="parse",
                failure_role="Developer",
            ),
        )
        # 2024-02: one card with attempts=1 (default) → 100%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_b",
                event_type="finished",
                timestamp="2024-02-07T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_rate_percent"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["values"][0]["sprint"] == "2024-01"
        assert body["values"][0]["value"] == 0
        assert isinstance(body["values"][0]["value"], int)
        assert not isinstance(body["values"][0]["value"], bool)
        assert body["values"][1]["sprint"] == "2024-02"
        assert body["values"][1]["value"] == 100
        assert isinstance(body["values"][1]["value"], int)
        assert not isinstance(body["values"][1]["value"], bool)
    finally:
        conn.close()


@requires_db
def test_trend_response_validates_against_schema():
    """AC4 (UX): a /trend response validates against TREND_SCHEMA with no errors."""
    import jsonschema
    import psycopg

    from sprint_metrics.schema import TREND_SCHEMA

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_schema_a', 'ac4_schema_b', 'ac4_schema_c')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Three sprints with one finished card each (throughput = 1 each)
        for sprint, card_id in [
            ("2024-01", "ac4_schema_a"),
            ("2024-02", "ac4_schema_b"),
            ("2024-03", "ac4_schema_c"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp=f"{sprint}-03T10:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp=f"{sprint}-07T15:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-03"
        )
        assert status == 200
        jsonschema.validate(instance=body, schema=TREND_SCHEMA)
    finally:
        conn.close()


@requires_db
def test_trend_registered_sprints_chronological_order():
    """AC2: Trend with registered sprints whose lexicographic order differs from
    chronological order returns values in start_date order."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac2_ts_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac2_ts_%'")
    conn.commit()

    upsert_sprint(conn, "ac2_ts_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac2_ts_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")
    upsert_sprint(conn, "ac2_ts_10", date(2024, 3, 1), date(2024, 3, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        for sprint, card_id in [
            ("ac2_ts_1", "ac2_ts_c1"),
            ("ac2_ts_2", "ac2_ts_c2"),
            ("ac2_ts_10", "ac2_ts_c3"),
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

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=ac2_ts_1&end=ac2_ts_10"
        )
        assert status == 200
        assert body["values"][0]["sprint"] == "ac2_ts_1"
        assert body["values"][1]["sprint"] == "ac2_ts_2"
        assert body["values"][2]["sprint"] == "ac2_ts_10"
    finally:
        conn.close()


@requires_db
def test_trend_all_sprints_have_events_returns_integers():
    """AC1: GET /trend?metric=cycle_time_days&start=2024-01&end=2024-02 with events
    in both sprints returns 200, Content-Type application/json, and the values array
    has exactly 2 entries: 2024-01 value 4, 2024-02 value 3."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_trend_ok_a', 'ac1_trend_ok_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created 2024-01-01, started 2024-01-02, finished 2024-01-06 → cycle 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: created 2024-02-01, started 2024-02-02, finished 2024-02-05 → cycle 3
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_b",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 4}
        assert body["values"][1] == {"sprint": "2024-02", "value": 3}
    finally:
        conn.close()


@requires_db
def test_trend_gap_sprint_returns_null():
    """AC3: GET /trend?metric=cycle_time_days&start=2026-10&end=2026-12 with events
    in 2026-10 and 2026-12 but not 2026-11 returns 200, Content-Type application/json,
    values array has exactly 3 entries: 2026-10 value 4, 2026-11 value null, 2026-12 value 2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac3_trend_gap_a', 'ac3_trend_gap_b')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: created 2026-10-07, started 2026-10-07, finished 2026-10-11 → cycle 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_a",
                event_type="started",
                timestamp="2026-10-07T10:00:00Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_a",
                event_type="finished",
                timestamp="2026-10-11T15:00:00Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # Sprint 2026-12: created 2026-12-01, started 2026-12-01, finished 2026-12-03 → cycle 2
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_b",
                event_type="started",
                timestamp="2026-12-01T10:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_b",
                event_type="finished",
                timestamp="2026-12-03T15:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        # Sprint 2026-11: no events

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2026-10&end=2026-12",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2026-10", "value": 4}
        assert body["values"][1] == {"sprint": "2026-11", "value": None}
        assert body["values"][2] == {"sprint": "2026-12", "value": 2}
    finally:
        conn.close()


@requires_db
def test_trend_single_sprint_with_events_returns_integer():
    """AC4: GET /trend?metric=throughput&start=2026-10&end=2026-10 with events in
    2026-10 returns 200, values array has exactly 1 entry, sprint 2026-10 value is
    integer 1 (not null)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_trend_single'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card, started and finished same day
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_trend_single",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_trend_single",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2026-10&end=2026-10"
        )
        assert status == 200
        assert len(body["values"]) == 1
        assert body["values"][0]["sprint"] == "2026-10"
        assert body["values"][0]["value"] == 1
        assert isinstance(body["values"][0]["value"], int)
        assert not isinstance(body["values"][0]["value"], bool)
    finally:
        conn.close()


@requires_db
def test_trend_points_delivered_two_sprints():
    """AC1+AC5: GET /trend?metric=points_delivered&start=2024-01&end=2024-02 with
    sprint 2024-01 having one finished card (points 5) and sprint 2024-02 having
    two finished cards (points 3 and 4) returns 200, Content-Type application/json,
    and values array has exactly two entries in order: 2024-01 value 5, 2024-02 value 7."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_pd_a', 'ac1_pd_b', 'ac1_pd_c')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: one finished card with points 5
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                points=5,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: two finished cards with points 3 and 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=3,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_c",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=4,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_c",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=points_delivered&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == API_VERSION
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 5}
        assert body["values"][1] == {"sprint": "2024-02", "value": 7}
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_denominator_two_sprints():
    """AC2: GET /trend?metric=first_attempt_denominator&start=2024-01&end=2024-02 with
    sprint 2024-01 having three finished cards and sprint 2024-02 having five finished
    cards returns 200 and values has 2024-01 value 3 and 2024-02 value 5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac2_fa_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: three finished cards
        for i in range(3):
            card_id = f"ac2_fa_{chr(ord('a') + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-03T10:00:00Z",
                    sprint="2024-01",
                    created="2024-01-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-07T15:00:00Z",
                    sprint="2024-01",
                    created="2024-01-01",
                ),
            )
        # Sprint 2024-02: five finished cards
        for i in range(5):
            card_id = f"ac2_fa_{chr(ord('a') + 3 + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-02-03T10:00:00Z",
                    sprint="2024-02",
                    created="2024-02-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-02-06T15:00:00Z",
                    sprint="2024-02",
                    created="2024-02-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_denominator"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 3}
        assert body["values"][1] == {"sprint": "2024-02", "value": 5}
    finally:
        conn.close()


@requires_db
def test_trend_refuses_metric_names_outside_the_accepted_measures():
    """AC3: accepting DORA's four measure names changes nothing about the
    refusal of a metric that is not one of the accepted measures: 400 with an
    'unknown metric' error naming the metric."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        for metric in ("lead_time_for_changes", "dora_recovery_minutes", "bogus_metric"):
            status, body = _get_json(
                f"http://127.0.0.1:{port}/trend?metric={metric}&start=2024-01&end=2024-02"
            )
            assert status == 400
            assert "unknown metric" in body["error"]
            assert metric in body["error"]
    finally:
        conn.close()
