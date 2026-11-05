"""Service tests for the dora answer on /range and DORA's four measures on /trend."""

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


def test_trend_description_lists_dora_metrics():
    """The /trend endpoint description in SERVICE_ENDPOINTS lists
    release_frequency and dora_lead_time_days as valid metrics."""
    from sprint_metrics.service import SERVICE_ENDPOINTS

    trend = next(desc for method, path, desc in SERVICE_ENDPOINTS if path == "/trend")
    assert "release_frequency" in trend, (
        "SERVICE_ENDPOINTS /trend description does not list release_frequency"
    )
    assert "dora_lead_time_days" in trend, (
        "SERVICE_ENDPOINTS /trend description does not list dora_lead_time_days"
    )


@requires_db
def test_range_dora_release_frequency_and_lead_time():
    """AC1: two epics release in a sprint (one with 3 stories, one with 1 story)
    yields release_frequency 2 and lead_time_days the mean of the four spans."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'd_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Epic A: 1 story, created 2024-01-01, finished 2024-01-05T00:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_a1",
                event_type="finished",
                timestamp="2024-01-05T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # Epic B: 3 stories
        # d_b1: created 2024-01-01, finished 2024-01-04T00:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_b1",
                event_type="finished",
                timestamp="2024-01-04T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E2"},
        )
        # d_b2: created 2024-01-02, finished 2024-01-05T00:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_b2",
                event_type="finished",
                timestamp="2024-01-05T00:00:00Z",
                sprint="2024-01",
                created="2024-01-02",
            ) | {"epic": "E2"},
        )
        # d_b3: created 2024-01-03, finished 2024-01-06T00:00:00Z (last story of E2)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_b3",
                event_type="finished",
                timestamp="2024-01-06T00:00:00Z",
                sprint="2024-01",
                created="2024-01-03",
            ) | {"epic": "E2"},
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        # Two epics release (E1 and E2)
        assert dora["release_frequency"] == 2
        # Spans: d_a1 = 4 days, d_b1 = 5 days, d_b2 = 4 days, d_b3 = 3 days
        # Mean = (4 + 5 + 4 + 3) / 4 = 4.0 → rounds to 4
        assert dora["lead_time_days"] == 4
    finally:
        conn.close()


@requires_db
def test_range_dora_null_when_no_epic_links():
    """AC2: a sprint whose events carry no epic link has DORA values null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'd_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # A finished story with no epic link
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_noepic",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_noepic",
                event_type="finished",
                timestamp="2024-01-07T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        # DORA block is present (sprint has events) but values are null
        assert dora is not None
        assert dora["release_frequency"] is None
        assert dora["lead_time_days"] is None
    finally:
        conn.close()


@requires_db
def test_range_dora_null_block_when_no_events():
    """AC2: a sprint with no events at all has the whole DORA block null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'd_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Only 2024-01 has events
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="d_ev1",
                event_type="finished",
                timestamp="2024-01-07T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        # 2024-02 has no events → dora is null
        assert body["sprints"]["2024-02"]["dora"] is None
        # 2024-01 has events with epic link → dora has values
        assert body["sprints"]["2024-01"]["dora"]["release_frequency"] == 1
    finally:
        conn.close()


@requires_db
def test_trend_release_frequency_and_lead_time():
    """The /trend endpoint returns correct values for release_frequency and
    dora_lead_time_days, not the failure_breakdown sum."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dtr_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: Epic E1 releases with one story (created 2024-01-01, finished 2024-01-05)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtr_a1",
                event_type="finished",
                timestamp="2024-01-05T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # 2024-02: Epic E2 releases with two stories
        # dtr_b1: created 2024-02-01, finished 2024-02-04
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtr_b1",
                event_type="finished",
                timestamp="2024-02-04T00:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ) | {"epic": "E2"},
        )
        # dtr_b2: created 2024-02-02, finished 2024-02-06 (last story of E2)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtr_b2",
                event_type="finished",
                timestamp="2024-02-06T00:00:00Z",
                sprint="2024-02",
                created="2024-02-02",
            ) | {"epic": "E2"},
        )

        # Query release_frequency across both sprints
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=release_frequency&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["metric"] == "release_frequency"
        assert body["values"][0] == {"sprint": "2024-01", "value": 1}
        assert body["values"][1] == {"sprint": "2024-02", "value": 1}

        # Query dora_lead_time_days across both sprints
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=dora_lead_time_days&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["metric"] == "dora_lead_time_days"
        # 2024-01: span = 4 days (Jan 1 to Jan 5)
        assert body["values"][0] == {"sprint": "2024-01", "value": 4}
        # 2024-02: spans = 3 days (Feb 1 to Feb 4) and 4 days (Feb 2 to Feb 6)
        # Mean = (3 + 4) / 2 = 3.5 → rounds to 4
        assert body["values"][1] == {"sprint": "2024-02", "value": 4}
    finally:
        conn.close()


def test_sprint_range_schema_declares_dora_on_sprint_entry():
    """AC4: SPRINT_RANGE_SCHEMA documents dora as an optional property per
    sprint entry (not in required), with all five DORA measures
    (integer-or-null)."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    # dora is NOT in the required list
    assert "dora" not in sprint_entry["required"]
    # dora is in properties
    dora_schema = sprint_entry["properties"]["dora"]
    assert dora_schema["type"] == ["object", "null"]
    assert dora_schema["required"] == [
        "release_frequency",
        "lead_time_days",
        "change_failure_count",
        "change_failure_rate_percent",
        "mean_time_to_recovery_minutes",
    ]
    assert dora_schema["properties"]["release_frequency"] == {
        "type": ["integer", "null"],
    }
    assert dora_schema["properties"]["lead_time_days"] == {
        "type": ["integer", "null"],
    }
    assert dora_schema["properties"]["change_failure_count"] == {
        "type": ["integer", "null"],
    }
    assert dora_schema["properties"]["change_failure_rate_percent"] == {
        "type": ["integer", "null"],
    }
    assert dora_schema["properties"]["mean_time_to_recovery_minutes"] == {
        "type": ["integer", "null"],
    }


@requires_db
def test_range_dora_change_failure_count_and_rate():
    """AC1: a sprint with two epic releases, one with a returned event after
    its release moment, reports change_failure_count 1 and rate 50."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dcf_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Epic E1: one story, finished 2024-01-10T00:00:00Z (release moment)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcf_e1s1",
                event_type="finished",
                timestamp="2024-01-10T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # Epic E1: a returned event on a story after the release moment
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcf_e1r1",
                event_type="returned",
                timestamp="2024-01-11T00:00:00Z",
                sprint="2024-01",
                created="2024-01-02",
            ) | {"epic": "E1"},
        )
        # Epic E2: one story, finished 2024-01-12T00:00:00Z (release moment)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcf_e2s1",
                event_type="finished",
                timestamp="2024-01-12T00:00:00Z",
                sprint="2024-01",
                created="2024-01-03",
            ) | {"epic": "E2"},
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        assert dora["release_frequency"] == 2
        assert dora["change_failure_count"] == 1
        assert dora["change_failure_rate_percent"] == 50
    finally:
        conn.close()


@requires_db
def test_range_dora_change_failure_zero_when_no_rework():
    """AC2: a sprint with releases but no returned event after release moments
    reports change_failure_count 0 and rate 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dcz_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Epic E1: one story, finished 2024-01-10T00:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcz_e1s1",
                event_type="finished",
                timestamp="2024-01-10T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # Epic E2: one story, finished 2024-01-12T00:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcz_e2s1",
                event_type="finished",
                timestamp="2024-01-12T00:00:00Z",
                sprint="2024-01",
                created="2024-01-02",
            ) | {"epic": "E2"},
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        assert dora["change_failure_count"] == 0
        assert dora["change_failure_rate_percent"] == 0
        assert dora["mean_time_to_recovery_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_dora_change_failure_null_when_no_releases():
    """AC2: a sprint with no releases at all reports JSON null for both."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dcn_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: Epic E1 releases (one story)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcn_e1s1",
                event_type="finished",
                timestamp="2024-01-10T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # 2024-02: no epic-link events (no releases)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dcn_noepic",
                event_type="finished",
                timestamp="2024-02-10T00:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        # 2024-01 has a release → has values
        dora1 = body["sprints"]["2024-01"]["dora"]
        assert dora1["release_frequency"] == 1
        assert dora1["change_failure_count"] == 0
        assert dora1["change_failure_rate_percent"] == 0
        # 2024-02 has no epic-link events → all DORA values null
        dora2 = body["sprints"]["2024-02"]["dora"]
        assert dora2 is not None
        assert dora2["release_frequency"] is None
        assert dora2["change_failure_count"] is None
        assert dora2["change_failure_rate_percent"] is None
        assert dora2["mean_time_to_recovery_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_dora_mttr_completed_recovery():
    """AC3: a bad release whose epic re-releases in a later sprint → MTTR is the recovery span in whole minutes."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dmt_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Epic E1: story 1 finished 2024-01-30T00:00:00Z (sprint 2024-01, release moment)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dmt_e1s1",
                event_type="finished",
                timestamp="2024-01-30T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # Epic E1: returned event 2024-01-31T00:00:00Z (after release moment, in sprint 2024-01)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dmt_e1r1",
                event_type="returned",
                timestamp="2024-01-31T00:00:00Z",
                sprint="2024-01",
                created="2024-01-02",
            ) | {"epic": "E1"},
        )
        # Epic E1: story 2 finished 2024-02-02T00:00:00Z (sprint 2024-02, re-release)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dmt_e1s2",
                event_type="finished",
                timestamp="2024-02-02T00:00:00Z",
                sprint="2024-02",
                created="2024-01-03",
            ) | {"epic": "E1"},
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        assert dora["change_failure_count"] == 1
        assert dora["change_failure_rate_percent"] == 100
        # Recovery span: 2024-02-02 - 2024-01-31 = 2 days = 2880 minutes
        assert dora["mean_time_to_recovery_minutes"] == 2880
    finally:
        conn.close()


@requires_db
def test_range_dora_mttr_none_when_no_completed_recovery():
    """AC3: a bad release whose epic never re-releases → MTTR is null (not zero)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dmt2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Epic E1: story 1 finished 2024-01-10T00:00:00Z (release moment)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dmt2_e1s1",
                event_type="finished",
                timestamp="2024-01-10T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        # Epic E1: returned event 2024-01-11T00:00:00Z (after release moment)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dmt2_e1r1",
                event_type="returned",
                timestamp="2024-01-11T00:00:00Z",
                sprint="2024-01",
                created="2024-01-02",
            ) | {"epic": "E1"},
        )
        # No re-release for E1

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        assert dora["change_failure_count"] == 1
        assert dora["change_failure_rate_percent"] == 100
        assert dora["mean_time_to_recovery_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_dora_change_failure_null_when_no_epic_links():
    """AC4: a sprint whose stories carry no epic link → all DORA values null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dnc_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # A finished story with no epic link
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dnc_s1",
                event_type="finished",
                timestamp="2024-01-07T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        dora = body["sprints"]["2024-01"]["dora"]
        assert dora is not None
        assert dora["release_frequency"] is None
        assert dora["lead_time_days"] is None
        assert dora["change_failure_count"] is None
        assert dora["change_failure_rate_percent"] is None
        assert dora["mean_time_to_recovery_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_trend_dora_measures_match_the_range_dora_values():
    """AC1: GET /trend answers each of DORA's four measures across a range of
    sprints with derivable values: one value per sprint, each value a whole
    number in the measure's unit equal to the same sprint's /range DORA value,
    and the response carries the service's api_version."""
    import psycopg

    from sprint_metrics.report import API_VERSION

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dtd_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: epics E1 and E2 release; E1 comes back with rework
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtd_e1s1",
                event_type="finished",
                timestamp="2024-01-30T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtd_e2s1",
                event_type="finished",
                timestamp="2024-01-12T00:00:00Z",
                sprint="2024-01",
                created="2024-01-05",
            ) | {"epic": "E2"},
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtd_e1r1",
                event_type="returned",
                timestamp="2024-01-31T00:00:00Z",
                sprint="2024-01",
                created="2024-01-02",
            ) | {"epic": "E1"},
        )
        # 2024-02: E1 re-releases (its recovery completes) and E3 releases
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtd_e1s2",
                event_type="finished",
                timestamp="2024-02-02T00:00:00Z",
                sprint="2024-02",
                created="2024-01-03",
            ) | {"epic": "E1"},
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtd_e3s1",
                event_type="finished",
                timestamp="2024-02-10T00:00:00Z",
                sprint="2024-02",
                created="2024-02-05",
            ) | {"epic": "E3"},
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        range_dora = {
            label: body["sprints"][label]["dora"] for label in ("2024-01", "2024-02")
        }

        # The /range values, in each measure's unit
        assert range_dora["2024-01"]["release_frequency"] == 1
        assert range_dora["2024-01"]["lead_time_days"] == 20
        assert range_dora["2024-01"]["change_failure_count"] == 1
        assert range_dora["2024-01"]["change_failure_rate_percent"] == 50
        assert range_dora["2024-01"]["mean_time_to_recovery_minutes"] == 2880
        assert range_dora["2024-02"]["release_frequency"] == 2
        assert range_dora["2024-02"]["lead_time_days"] == 18
        assert range_dora["2024-02"]["change_failure_count"] == 0
        assert range_dora["2024-02"]["change_failure_rate_percent"] == 0
        assert range_dora["2024-02"]["mean_time_to_recovery_minutes"] is None

        trend_metric_to_range_key = {
            "release_frequency": "release_frequency",
            "dora_lead_time_days": "lead_time_days",
            "change_failure_count": "change_failure_count",
            "change_failure_rate_percent": "change_failure_rate_percent",
            "mean_time_to_recovery_minutes": "mean_time_to_recovery_minutes",
        }
        for metric, range_key in trend_metric_to_range_key.items():
            status, body = _get_json(
                f"http://127.0.0.1:{port}/trend?metric={metric}&start=2024-01&end=2024-02"
            )
            assert status == 200
            assert body["api_version"] == API_VERSION
            assert body["metric"] == metric
            assert [entry["sprint"] for entry in body["values"]] == ["2024-01", "2024-02"]
            for entry in body["values"]:
                assert entry["value"] == range_dora[entry["sprint"]][range_key]
                if entry["value"] is not None:
                    assert type(entry["value"]) is int, (
                        f"{metric} for {entry['sprint']} is not a whole number"
                    )
    finally:
        conn.close()


@requires_db
def test_trend_dora_measures_null_where_no_data_other_sprints_answered():
    """AC2: a sprint with no stored events, and a sprint whose stored stories
    carry no derivable epic link, read JSON null for each DORA measure while
    the other sprints in the range are still answered."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'dtn_%'")
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN "
        "('2024-01', '2024-02', '2024-03', '2024-04')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: E1 releases and comes back with rework; E2 releases
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtn_e1s1",
                event_type="finished",
                timestamp="2024-01-15T00:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ) | {"epic": "E1"},
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtn_e1r1",
                event_type="returned",
                timestamp="2024-01-16T00:00:00Z",
                sprint="2024-01",
                created="2024-01-05",
            ) | {"epic": "E1"},
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtn_e2s1",
                event_type="finished",
                timestamp="2024-01-20T00:00:00Z",
                sprint="2024-01",
                created="2024-01-10",
            ) | {"epic": "E2"},
        )
        # 2024-02: no events at all
        # 2024-03: events, but the stored story carries no epic link
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtn_plain",
                event_type="finished",
                timestamp="2024-03-10T00:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        # 2024-04: E1 re-releases (its recovery completes) and E3 releases
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtn_e1s2",
                event_type="finished",
                timestamp="2024-04-02T00:00:00Z",
                sprint="2024-04",
                created="2024-01-20",
            ) | {"epic": "E1"},
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="dtn_e3s1",
                event_type="finished",
                timestamp="2024-04-20T00:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ) | {"epic": "E3"},
        )

        answered = {
            "release_frequency": {"2024-01": 1, "2024-04": 2},
            "dora_lead_time_days": {"2024-01": 51, "2024-04": 46},
            "change_failure_count": {"2024-01": 1, "2024-04": 0},
            "change_failure_rate_percent": {"2024-01": 50, "2024-04": 0},
            "mean_time_to_recovery_minutes": {"2024-01": 110880},
        }
        for metric, expected_values in answered.items():
            status, body = _get_json(
                f"http://127.0.0.1:{port}/trend?metric={metric}&start=2024-01&end=2024-04"
            )
            assert status == 200
            values = {entry["sprint"]: entry["value"] for entry in body["values"]}
            assert values["2024-02"] is None, (
                f"{metric}: the sprint with no events is not JSON null"
            )
            assert values["2024-03"] is None, (
                f"{metric}: the sprint with no derivable epic link is not JSON null"
            )
            for label, expected in expected_values.items():
                assert values[label] == expected, (
                    f"{metric}: {label} not answered with {expected!r} (got {values[label]!r})"
                )
    finally:
        conn.close()
