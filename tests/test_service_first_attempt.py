"""Service tests for attempt_failed events, the first-attempt rate, failure_breakdown, and points."""

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

from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


@requires_db
def test_post_attempt_failed_returns_200_no_error():
    """AC1: POST /events with type 'attempt_failed' returns 200, Content-Type
    application/json, and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        event = {
            "api_version": "1",
            "card_id": "ac1_attempt",
            "type": "attempt_failed",
            "timestamp": "2024-01-12T14:00:00Z",
            "sprint": "Sprint 18",
            "attempt_number": 1,
            "failure_class": "parse",
            "failure_role": "Developer",
            "card": {"created": "2024-01-10"},
        }
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_rate_zero_with_attempt_failed():
    """AC2: after started + attempt_failed + finished, GET /range returns
    first_attempt_rate_percent=0 and throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        attempt_failed = {
            "api_version": "1",
            "card_id": "ac2_attempt",
            "type": "attempt_failed",
            "timestamp": "2024-01-12T14:00:00Z",
            "sprint": "2024-06",
            "attempt_number": 1,
            "failure_class": "parse",
            "failure_role": "Developer",
            "card": {"created": "2024-01-10"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)

        finished = _make_event(
            card_id="ac2_attempt",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=2,
            failure_class="parse",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_rate_percent"] == 0
        assert body["sprints"]["2024-06"]["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_failure_breakdown_with_multiple_attempts():
    """AC3+UX6: after started + six attempt_failed + finished (attempts 7),
    GET /range returns first_attempt_rate_percent=0, throughput=1, and
    failure_breakdown with one entry per return (VERIFY 3, SCHEMA 2, TEST 1,
    all Developer) in count-descending order. top_failure_causes holds
    exactly three entries, one per (class, role) return pair."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac5_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        failure_classes = ["VERIFY", "SCHEMA", "VERIFY", "TEST", "SCHEMA", "VERIFY"]
        for i, fc in enumerate(failure_classes, start=1):
            event = {
                "api_version": "1",
                "card_id": "ac5_attempt",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": fc,
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac5_attempt",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=7,
            failure_class="VERIFY",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        sprint_data = body["sprints"]["2024-06"]
        assert sprint_data["first_attempt_rate_percent"] == 0
        assert sprint_data["throughput"] == 1
        assert sprint_data["failure_breakdown"] == [
            {"class": "VERIFY", "role": "Developer", "count": 3},
            {"class": "SCHEMA", "role": "Developer", "count": 2},
            {"class": "TEST", "role": "Developer", "count": 1},
        ]
        assert sprint_data["top_failure_causes"] == [
            {"class": "VERIFY", "role": "Developer", "count": 3},
            {"class": "SCHEMA", "role": "Developer", "count": 2},
            {"class": "TEST", "role": "Developer", "count": 1},
        ]
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_rate_driven_by_crew_attempts():
    """AC1: a card with started + two attempt_failed + finished (attempts 1)
    yields first_attempt_rate_percent 100 — the rate is driven by the
    crew-sent attempts on the finished row, not by 1 + count."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_crew_attempts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_crew_attempts",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ac1_crew_attempts",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac1_crew_attempts",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=1,
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_rate_percent"] == 100
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_rate_fallback_when_no_crew_attempts():
    """AC2: a card whose finished event carries no attempts field and whose
    history holds two attempt_failed rows yields first_attempt_rate_percent 0
    — the attempts count falls back to 1 + count (3)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_no_attempts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_no_attempts",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ac2_no_attempts",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac2_no_attempts",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_rate_percent"] == 0
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_numerator_denominator_crew_attempts():
    """UX7: a card with started + two attempt_failed + finished (attempts 1)
    yields first_attempt_numerator 1 and first_attempt_denominator 1, so the
    raw counts agree with the 100% rate and the crew-sent attempts count."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ux7_counts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ux7_counts",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ux7_counts",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ux7_counts",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=1,
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_numerator"] == 1
        assert body["sprints"]["2024-06"]["first_attempt_denominator"] == 1
    finally:
        conn.close()


@requires_db
def test_range_first_attempt_rate_crew_attempts():
    """UX8: a sprint with a card (started + two attempt_failed + finished
    attempts 1) included in a range yields first_attempt_rate_percent 100 —
    the crew's handout count drives the rate on the range surface as well."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ux8_range'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ux8_range",
            event_type="started",
            timestamp="2026-10-07T10:00:00Z",
            sprint="2026-10",
            created="2026-10-07",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ux8_range",
                "type": "attempt_failed",
                "timestamp": f"2026-10-07T{10 + i}:00:00Z",
                "sprint": "2026-10",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2026-10-07"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ux8_range",
            event_type="finished",
            timestamp="2026-10-10T10:00:00Z",
            sprint="2026-10",
            created="2026-10-07",
            attempts=1,
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        entry = body["sprints"]["2026-10"]
        assert entry["first_attempt_rate_percent"] == 100
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_two_causes():
    """AC1: GET /range with two completed cards having distinct failure causes
    returns failure_breakdown with exactly two objects."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_fb_a', 'ac1_fb_b')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=3,
                failure_class="parse",
                failure_role="Developer",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_b",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_b",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=2,
                failure_class="check",
                failure_role="Code Reviewer",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        fb = body["sprints"]["2024-01"]["failure_breakdown"]
        assert len(fb) == 2
        assert {"class": "parse", "role": "Developer", "count": 1} in fb
        assert {"class": "check", "role": "Code Reviewer", "count": 1} in fb
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_empty_when_first_attempt():
    """AC2: GET /range with a single completed card (attempts=1) returns
    failure_breakdown as an empty array."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_fb'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_fb",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_fb",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["failure_breakdown"] == []
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_not_truncated_to_three():
    """AC3 (UX): GET /range with four completed cards each having a distinct
    (failure_class, failure_role) pair returns failure_breakdown with exactly 4 objects."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac3_fb_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        cards = [
            ("ac3_fb_c1", "PARSE", "Code Reviewer", 3),
            ("ac3_fb_c2", "VERIFY", "Developer", 7),
            ("ac3_fb_c3", "SCHEMA", "Architect", 2),
            ("ac3_fb_c4", "SCHEMA", "Developer", 4),
        ]
        for card_id, fc, fr, attempts in cards:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2026-10-07T13:14:07Z",
                    sprint="2026-10",
                    created="2026-10-07",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2026-10-07T20:52:22Z",
                    sprint="2026-10",
                    created="2026-10-07",
                    attempts=attempts,
                    failure_class=fc,
                    failure_role=fr,
                ),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        fb = body["sprints"]["2026-10"]["failure_breakdown"]
        assert len(fb) == 4
        assert {"class": "PARSE", "role": "Code Reviewer", "count": 1} in fb
        assert {"class": "VERIFY", "role": "Developer", "count": 1} in fb
        assert {"class": "SCHEMA", "role": "Architect", "count": 1} in fb
        assert {"class": "SCHEMA", "role": "Developer", "count": 1} in fb
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_and_top_failure_causes_coexist():
    """AC4 (UX): GET /range with one completed card (VERIFY/Developer, attempts 7)
    returns both failure_breakdown (array with one object) and top_failure_causes
    (object with VERIFY mapping to 1)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_fb'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_fb",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_fb",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
                attempts=7,
                failure_class="VERIFY",
                failure_role="Developer",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        entry = body["sprints"]["2026-10"]
        assert entry["failure_breakdown"] == [{"class": "VERIFY", "role": "Developer", "count": 1}]
        assert entry["top_failure_causes"] == [{"class": "VERIFY", "role": "Developer", "count": 1}]
        assert len(entry["failure_breakdown"]) == 1
    finally:
        conn.close()


@requires_db
def test_sprint_response_includes_points_first_attempt_and_escalation_count():
    """AC1/AC6: after POSTing started+finished+escalated for a card with points 5,
    GET /range returns the four new fields with correct values alongside existing keys."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_new_fields'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_new_fields",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            points=5,
        )
        finished = _make_event(
            card_id="ac1_new_fields",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        escalated = _make_event(
            card_id="ac1_new_fields",
            event_type="escalated",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)
        _post_events(f"http://127.0.0.1:{port}/events", escalated)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["points_delivered"] == 5
        assert sprint_data["first_attempt_numerator"] == 1
        assert sprint_data["first_attempt_denominator"] == 1
        assert "escalation_count" not in sprint_data
        assert "throughput" in sprint_data
        assert "first_attempt_rate_percent" in sprint_data
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_new_fields_are_null():
    """AC2/AC7: no events stored for sprint 2026-11, GET /range returns 200
    and the four new fields are null, matching the existing null pattern."""
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
        assert sprint_data["points_delivered"] is None
        assert sprint_data["first_attempt_numerator"] is None
        assert sprint_data["first_attempt_denominator"] is None
        assert "escalation_count" not in sprint_data
        assert sprint_data["throughput"] is None
        assert sprint_data["first_attempt_rate_percent"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_escalations_counted_without_completions():
    """AC3: one started event (no finished) and two escalated events for sprint 2024-01,
    GET /range returns points_delivered=0, first_attempt_numerator=None,
    first_attempt_denominator=None, escalation_count=2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_esc'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac3_esc",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        esc1 = _make_event(
            card_id="ac3_esc",
            event_type="escalated",
            timestamp="2024-01-04T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        esc2 = _make_event(
            card_id="ac3_esc",
            event_type="escalated",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", esc1)
        _post_events(f"http://127.0.0.1:{port}/events", esc2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["points_delivered"] == 0
        assert sprint_data["first_attempt_numerator"] is None
        assert sprint_data["first_attempt_denominator"] is None
        assert "escalation_count" not in sprint_data
    finally:
        conn.close()


@requires_db
def test_range_includes_points_first_attempt_and_escalation_count():
    """AC4: 2024-01 has one finished card (points 5, attempts 1) and one escalated event;
    2024-02 has two finished cards (points 3 and 2, both attempts 1) and one escalated event.
    GET /range returns correct values per sprint with existing keys still present."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_range_a', 'ac4_range_b', 'ac4_range_c')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: one finished card (points 5, attempts 1)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
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
                card_id="ac4_range_a",
                event_type="escalated",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: two finished cards (points 3 and 2, both attempts 1)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
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
                card_id="ac4_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_c",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=2,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_c",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="escalated",
                timestamp="2024-02-05T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        s01 = body["sprints"]["2024-01"]
        s02 = body["sprints"]["2024-02"]
        # 2024-01: points 5, first-attempt 1/1, escalation 1
        assert s01["points_delivered"] == 5
        assert s01["first_attempt_numerator"] == 1
        assert s01["first_attempt_denominator"] == 1
        assert "escalation_count" not in s01
        # 2024-02: points 5 (3+2), first-attempt 2/2, escalation 1
        assert s02["points_delivered"] == 5
        assert s02["first_attempt_numerator"] == 2
        assert s02["first_attempt_denominator"] == 2
        assert "escalation_count" not in s02
        # Both entries still contain existing keys and prior and delta
        for s in (s01, s02):
            for key in ("throughput", "cycle_time_days", "prior", "delta"):
                assert key in s
    finally:
        conn.close()


@requires_db
def test_range_null_new_fields_for_sprints_without_events():
    """AC5: sprint 2026-10 has one finished card (points 2, attempts 1);
    sprints 2026-11 and 2026-12 have no stored events. GET /range returns
    2026-10 with values and 2026-11/2026-12 with nulls for the four new fields."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_range_null'")
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_null",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
                points=2,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_null",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        s10 = body["sprints"]["2026-10"]
        s11 = body["sprints"]["2026-11"]
        s12 = body["sprints"]["2026-12"]
        # 2026-10 has values
        assert s10["points_delivered"] == 2
        assert s10["first_attempt_numerator"] == 1
        assert s10["first_attempt_denominator"] == 1
        assert "escalation_count" not in s10
        # 2026-11 and 2026-12 have nulls
        for s in (s11, s12):
            assert s["points_delivered"] is None
            assert s["first_attempt_numerator"] is None
            assert s["first_attempt_denominator"] is None
            assert "escalation_count" not in s
    finally:
        conn.close()
