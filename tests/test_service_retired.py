"""Service tests for what was retired: GET /sprint and GET /metrics answer 410, and the escalation measures."""

from __future__ import annotations

import pytest
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
def test_get_sprint_returns_410_with_label():
    """AC1: GET /sprint?label=2024-01 returns 410 with error naming the removal
    and pointing to GET /range."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 410
        assert "error" in body
        assert "removed" in body["error"]
        assert "/range" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_returns_410_without_query_string():
    """AC2: GET /sprint with no query string returns 410 without a database query."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint")
        assert status == 410
        assert "error" in body
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_returns_410_when_db_unreachable():
    """AC2: GET /sprint?label=2024-01 with unreachable DB returns the same 410
    answer without a database query being attempted."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 410
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_no_query_string_returns_410_not_400():
    """AC2: GET /sprint (no label at all) is answered 410, distinct from the 400
    validation answer and the 503/500 conditions."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint")
        assert status == 410
        assert status not in (200, 400, 404, 500, 503)
        assert "error" in body
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_empty_label_returns_410():
    """AC2: GET /sprint?label= (empty label) is answered 410 without a database
    query, the same as a missing label."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=")
        assert status == 410
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
@pytest.mark.parametrize("path", ["/metrics", "/metrics?sprint=2024-01", "/metrics?"])
def test_get_metrics_returns_410_with_or_without_query_string(path):
    """#764 AC1: GET /metrics, with or without a query string, returns 410 with
    an error saying the endpoint has been removed, even with stored events."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        for event in (
            _make_event("c1", "started", "2024-01-03T10:00:00Z"),
            _make_event("c1", "finished", "2024-01-05T10:00:00Z"),
        ):
            assert _post_events(f"{base}/events", event)[0] == 200

        status, body = _get_json(f"{base}{path}")
        assert status == 410
        assert status not in (200, 400, 404, 500, 503)
        assert "endpoint removed" in body["error"]
        assert "/metrics" in body["error"]
    finally:
        conn.close()


@requires_db
def test_get_metrics_returns_410_when_db_unreachable():
    """#764 AC1: GET /metrics with the database unreachable is answered the same
    410, without a database query being attempted."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    status, body = _get_json(f"http://127.0.0.1:{port}/metrics")
    assert status == 410
    assert "endpoint removed" in body["error"]


def test_no_route_builds_prometheus_text_from_stored_events():
    """#764 AC5: the service no longer carries a Prometheus text formatter for
    stored events, and GET /metrics is gone from the endpoint list."""
    import sprint_metrics.service as service

    assert not hasattr(service, "_metrics_text")
    assert ("GET", "/metrics") not in [(m, p) for m, p, _ in service.SERVICE_ENDPOINTS]


@requires_db
def test_range_carries_no_escalation_keys_in_entry_prior_or_delta():
    """#774 AC1-AC3, AC5: with 2 escalated events and 1 completed card in the later
    sprint, /range carries no escalation key in any entry, prior or delta, keeps
    every kept measure, and an event-free sprint still answers null for them."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        events = [
            ("e1", "started", "2024-01-03T10:00:00Z", "2024-01"),
            ("e1", "finished", "2024-01-05T10:00:00Z", "2024-01"),
            ("e2", "started", "2024-02-03T10:00:00Z", "2024-02"),
            ("e2", "escalated", "2024-02-04T10:00:00Z", "2024-02"),
            ("e2", "escalated", "2024-02-05T10:00:00Z", "2024-02"),
            ("e2", "finished", "2024-02-06T10:00:00Z", "2024-02"),
        ]
        for event in events:
            status, _ = _post_events(f"http://127.0.0.1:{port}/events", _make_event(*event))
            assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-03")
        assert status == 200
        labels = ("2024-01", "2024-02", "2024-03")
        first, later, empty = (body["sprints"][label] for label in labels)
        assert first["prior"] is None and first["delta"] is None
        for part in (first, later, empty, later["prior"], later["delta"]):
            assert "escalation_rate_percent" not in part
            assert "escalation_count" not in part
        kept = (
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "points_delivered",
            "first_attempt_numerator",
            "first_attempt_denominator",
            "first_attempt_rate_percent",
            "superseded_count",
            "superseded_points",
            "superseded_breakdown",
            "cycle_time_minutes",
            "lead_time_minutes",
            "failure_breakdown",
            "top_failure_causes",
            "story_costs",
            "cost",
        )
        for key in kept:
            assert key in later
        assert later["throughput"] == 1
        assert later["cycle_time_days"] == 3
        for key in ("cycle_time_days", "throughput", "points_delivered", "first_attempt_rate_percent"):
            assert empty[key] is None
    finally:
        conn.close()


@requires_db
def test_range_flags_do_not_depend_on_escalated_events():
    """#775 AC1, AC3: two sprints identical in every kept measure, one with 3
    escalated events, answer identical flags, each with exactly the eight kept
    measures and no escalation key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        events = []
        for sprint in ("2024-01", "2024-02"):
            card = f"f-{sprint}"
            events.append((card, "started", f"{sprint}-03T10:00:00Z", sprint, f"{sprint}-01"))
            events.append((card, "finished", f"{sprint}-05T10:00:00Z", sprint, f"{sprint}-01"))
        for hour in ("11", "12", "13"):
            timestamp = f"2024-02-04T{hour}:00:00Z"
            events.append(("f-2024-02", "escalated", timestamp, "2024-02", "2024-02-01"))
        for event in events:
            status, _ = _post_events(f"http://127.0.0.1:{port}/events", _make_event(*event))
            assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        quiet, escalated = body["sprints"]["2024-01"]["flags"], body["sprints"]["2024-02"]["flags"]
        assert quiet == escalated
        assert sorted(escalated) == sorted(
            [
                "cycle_time_days",
                "lead_time_days",
                "cycle_time_minutes",
                "lead_time_minutes",
                "throughput",
                "wip_violations",
                "blocked_aging_days",
                "first_attempt_rate_percent",
            ]
        )
    finally:
        conn.close()


@requires_db
@pytest.mark.parametrize("metric", ["escalation_rate_percent", "escalation_count"])
def test_trend_refuses_the_escalation_measures(metric):
    """#776 AC1: GET /trend for either escalation measure answers 400 naming the
    measure and saying it is no longer accepted, with no retryable flag."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric={metric}&start=2024-01&end=2024-02"
        )
        assert status == 400
        assert metric in body["error"]
        assert "no longer accepted" in body["error"]
        assert "retryable" not in body
    finally:
        conn.close()


@requires_db
def test_trend_answers_api_version_4_and_still_refuses_escalation_count():
    """#778 AC2: a kept-metric /trend answers 200 with api_version "4" and null
    for an event-free sprint, and escalation_count still answers 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        for event in (
            ("v1", "started", "2024-01-03T10:00:00Z"),
            ("v1", "finished", "2024-01-05T10:00:00Z"),
        ):
            assert _post_events(f"{base}/events", _make_event(*event))[0] == 200
        status, body = _get_json(f"{base}/trend?metric=throughput&start=2024-01&end=2024-02")
        assert status == 200
        assert body["api_version"] == API_VERSION
        assert body["values"] == [
            {"sprint": "2024-01", "value": 1},
            {"sprint": "2024-02", "value": None},
        ]
        status, _ = _get_json(f"{base}/trend?metric=escalation_count&start=2024-01&end=2024-02")
        assert status == 400
    finally:
        conn.close()


def test_trend_accepts_no_escalation_measure():
    """#776 AC3, AC4: neither escalation name is an accepted trend metric, and the
    /trend endpoint description no longer lists them."""
    from sprint_metrics.metrics import ALL_METRICS
    from sprint_metrics.service import SERVICE_ENDPOINTS

    assert "escalation_rate_percent" not in ALL_METRICS
    assert "escalation_count" not in ALL_METRICS
    trend = next(desc for method, path, desc in SERVICE_ENDPOINTS if path == "/trend")
    assert "escalation" not in trend


@requires_db
def test_escalated_event_is_stored_but_feeds_no_response():
    """#777 AC3: an escalated event is accepted and stored as before, but no
    /range field and no kept /trend value depends on it."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        for event in (
            ("x1", "started", "2024-01-03T10:00:00Z"),
            ("x1", "finished", "2024-01-05T10:00:00Z"),
        ):
            assert _post_events(f"{base}/events", _make_event(*event))[0] == 200
        _, range_before = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        _, trend_before = _get_json(f"{base}/trend?metric=throughput&start=2024-01&end=2024-01")

        escalated = _make_event("x1", "escalated", "2024-01-04T10:00:00Z")
        assert _post_events(f"{base}/events", escalated) == (200, {})
        stored = conn.execute(
            "SELECT COUNT(*) FROM sprint_metrics.board_events WHERE type = 'escalated'"
        ).fetchone()[0]
        assert stored == 1

        _, range_after = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        _, trend_after = _get_json(f"{base}/trend?metric=throughput&start=2024-01&end=2024-01")
        assert range_after == range_before
        assert trend_after == trend_before
        assert "escalation_count" not in range_after["sprints"]["2024-01"]
    finally:
        conn.close()


@requires_db
def test_service_escalation_rate_200_on_sprint_range_and_trend():
    """AC3 (#774, #776): sprint 2024-01 has one completed card and 2 escalated
    events; /range carries no escalation rate and /trend refuses it with 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_esc_rate'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Post started, finished, and 2 escalated events for one card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="escalated",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="escalated",
                timestamp="2024-01-06T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        # /range
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert "escalation_rate_percent" not in body["sprints"]["2024-01"]

        # /trend
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=escalation_rate_percent&start=2024-01&end=2024-01"
        )
        assert status == 400
    finally:
        conn.close()
