"""Service tests for GET /range's window object: its verdicts and standouts."""

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
from sprint_metrics.verdict import MEASURE_REGISTRY


@requires_db
def test_range_window_with_gap():
    """AC1: GET /range?start=2024-01&end=2024-03 with events in 2024-01 and 2024-03
    but not 2024-02 returns window.start='2024-01', window.end='2024-03',
    window.sprint_count=3, and window.no_data=['2024-02']."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('w_gap_a', 'w_gap_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="w_gap_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="w_gap_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="w_gap_b",
                event_type="started",
                timestamp="2024-03-03T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="w_gap_b",
                event_type="finished",
                timestamp="2024-03-07T15:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-03")
        assert status == 200
        assert body["window"]["start"] == "2024-01"
        assert body["window"]["end"] == "2024-03"
        assert body["window"]["sprint_count"] == 3
        assert body["window"]["no_data"] == ["2024-02"]
    finally:
        conn.close()


@requires_db
def test_range_window_empty_db():
    """AC3: GET /range?start=2024-01&end=2024-02 on an empty DB returns 200;
    window names both labels, sprint_count 2, no_data names both; every per-sprint
    metric value is null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["window"]["start"] == "2024-01"
        assert body["window"]["end"] == "2024-02"
        assert body["window"]["sprint_count"] == 2
        assert body["window"]["no_data"] == ["2024-01", "2024-02"]
        entry = body["sprints"]["2024-01"]
        assert entry["cycle_time_days"] is None
        assert entry["throughput"] is None
        assert entry["story_costs"] == []
        assert entry["cost"] is None
    finally:
        conn.close()


@requires_db
def test_range_window_verdict_judges_first_and_last_data_bearing():
    """AC1: with events in 2024-01 (cycle_time_days 10) and 2024-03 (6) and none
    in 2024-02, the window's cycle_time_days verdict is "better" and names the
    first data-bearing sprint 2024-01 (value 10) and the last 2024-03 (value 6),
    with unit days and precision whole; the gap sprint 2024-02 is skipped, not
    read as zero. Also proves AC5 (one entry per registry measure, none for the
    non-scalar items) and AC6 (each non-null entry carries exactly the verdict,
    the two reference sprints and values, the unit and the precision)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('v1_a', 'v1_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v1_a",
                event_type="started",
                timestamp="2024-01-01T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v1_a",
                event_type="finished",
                timestamp="2024-01-11T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v1_b",
                event_type="started",
                timestamp="2024-03-01T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v1_b",
                event_type="finished",
                timestamp="2024-03-07T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-03")
        assert status == 200
        assert body["window"]["no_data"] == ["2024-02"]
        verdicts = body["window"]["verdicts"]
        assert verdicts["cycle_time_days"] == {
            "verdict": "better",
            "first_sprint": "2024-01",
            "last_sprint": "2024-03",
            "first_value": 10,
            "last_value": 6,
            "unit": "days",
            "precision": "whole",
        }
        # AC5: exactly one entry per registry measure, keyed by name, and none
        # for the non-scalar items.
        assert set(verdicts) == set(MEASURE_REGISTRY)
        for non_scalar in (
            "failure_breakdown",
            "top_failure_causes",
            "superseded_breakdown",
            "story_costs",
        ):
            assert non_scalar not in verdicts
        # AC6: each non-null entry is self-contained with exactly these keys.
        for entry in verdicts.values():
            if entry is not None:
                assert set(entry) == {
                    "verdict",
                    "first_sprint",
                    "last_sprint",
                    "first_value",
                    "last_value",
                    "unit",
                    "precision",
                }
    finally:
        conn.close()


@requires_db
def test_range_window_verdicts_judged_against_their_direction():
    """AC2: judged against each measure's better direction — the last
    data-bearing sprint's throughput is higher (better), its
    first_attempt_rate_percent is lower (worse, higher-is-better), its
    model_minutes_total is higher (up, a movement-only measure), and a measure
    equal in both reference sprints (points_delivered) reads flat."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.store import upsert_session

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-01', '2024-02')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('v2_a1', 'v2_b1', 'v2_b2')"
    )
    conn.commit()

    # 2024-01: one story with a delivery session (600 model seconds -> 10 min)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, points, attempts)
           VALUES ('v2_a1', 'started', %s, '2024-01', '2024-01-01', 5, 1)""",
        (datetime(2024, 1, 2, 10, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "v2_a1",
            "role": "Developer",
            "start": "2024-01-02T11:00:00Z",
            "end": "2024-01-02T12:00:00Z",
            "sprint": "2024-01",
            "model_seconds": 600,
            "input_tokens": 1000,
            "output_tokens": 500,
        },
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, points, attempts)
           VALUES ('v2_a1', 'finished', %s, '2024-01', '2024-01-01', 5, 1)""",
        (datetime(2024, 1, 5, 10, 0, tzinfo=UTC),),
    )
    # 2024-02: two stories with delivery sessions (1800+1200=3000 model seconds -> 50 min)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, points, attempts)
           VALUES ('v2_b1', 'started', %s, '2024-02', '2024-02-01', 3, 1)""",
        (datetime(2024, 2, 2, 10, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "v2_b1",
            "role": "Developer",
            "start": "2024-02-02T11:00:00Z",
            "end": "2024-02-02T12:00:00Z",
            "sprint": "2024-02",
            "model_seconds": 1800,
            "input_tokens": 1000,
            "output_tokens": 500,
        },
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, points, attempts)
           VALUES ('v2_b1', 'finished', %s, '2024-02', '2024-02-01', 3, 1)""",
        (datetime(2024, 2, 5, 10, 0, tzinfo=UTC),),
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, points, attempts)
           VALUES ('v2_b2', 'started', %s, '2024-02', '2024-02-01', 2, 2)""",
        (datetime(2024, 2, 2, 10, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "v2_b2",
            "role": "Developer",
            "start": "2024-02-02T11:00:00Z",
            "end": "2024-02-02T12:00:00Z",
            "sprint": "2024-02",
            "model_seconds": 1200,
            "input_tokens": 1000,
            "output_tokens": 500,
        },
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created, points, attempts)
           VALUES ('v2_b2', 'finished', %s, '2024-02', '2024-02-01', 2, 2)""",
        (datetime(2024, 2, 5, 10, 0, tzinfo=UTC),),
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        verdicts = body["window"]["verdicts"]
        assert verdicts["throughput"]["verdict"] == "better"
        assert verdicts["first_attempt_rate_percent"]["verdict"] == "worse"
        assert verdicts["model_minutes_total"]["verdict"] == "up"
        assert verdicts["points_delivered"]["verdict"] == "flat"
        assert verdicts["throughput"]["first_value"] == 1
        assert verdicts["throughput"]["last_value"] == 2
        assert verdicts["first_attempt_rate_percent"]["first_value"] == 100
        assert verdicts["first_attempt_rate_percent"]["last_value"] == 50
        assert verdicts["model_minutes_total"]["first_value"] == 10
        assert verdicts["model_minutes_total"]["last_value"] == 50
    finally:
        conn.close()


@requires_db
def test_range_window_verdict_null_when_reference_value_missing():
    """AC3: cycle_time_minutes is null in the window's first data-bearing sprint
    (no card carries both sub-day timestamps) and a number in its last; the
    verdict entry for cycle_time_minutes is null — no verdict is computed against
    a missing number — while throughput still carries its verdict."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('v3_a', 'v3_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01 (first): finished event only -> the card is completed
        # (throughput 1) but carries no started_at, so cycle_time_minutes is null.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v3_a",
                event_type="finished",
                timestamp="2024-01-07T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-03 (last): started + finished -> cycle_time_minutes is a number.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v3_b",
                event_type="started",
                timestamp="2024-03-03T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v3_b",
                event_type="finished",
                timestamp="2024-03-07T15:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-03")
        assert status == 200
        assert body["sprints"]["2024-01"]["cycle_time_minutes"] is None
        assert isinstance(body["sprints"]["2024-03"]["cycle_time_minutes"], int)
        verdicts = body["window"]["verdicts"]
        assert verdicts["cycle_time_minutes"] is None
        assert verdicts["throughput"] is not None
    finally:
        conn.close()


@requires_db
def test_range_window_single_data_bearing_sprint_verdicts_all_null():
    """AC4: a window with exactly one data-bearing sprint answers 200, the
    window object is present, and every measure's verdict entry is null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'v4_a'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v4_a",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="v4_a",
                event_type="finished",
                timestamp="2024-02-06T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["window"]["sprint_count"] == 2
        assert body["window"]["no_data"] == ["2024-01"]
        verdicts = body["window"]["verdicts"]
        assert set(verdicts) == set(MEASURE_REGISTRY)
        assert all(entry is None for entry in verdicts.values())
    finally:
        conn.close()


@requires_db
def test_range_window_standouts_biggest_improvement_and_worst_dip():
    """AC1: with events in four sprints carrying throughput 4, 5, 3, 8 and
    cycle_time_days 9, 8, 8, 7, the window's biggest_improvement names
    throughput (2024-03 to 2024-04, size 5, count, whole); the worst_dip
    names throughput (2024-02 to 2024-03, size 2, count, whole)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'so_%'"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: throughput 4, cycle 9 days (started 01-01, finished 01-10)
        for i in range(4):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_a{i}", event_type="started", timestamp="2024-01-01T10:00:00Z", sprint="2024-01", created="2024-01-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_a{i}", event_type="finished", timestamp="2024-01-10T10:00:00Z", sprint="2024-01", created="2024-01-01"),
            )
        # 2024-02: throughput 5, cycle 8 days (started 02-01, finished 02-09)
        for i in range(5):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_b{i}", event_type="started", timestamp="2024-02-01T10:00:00Z", sprint="2024-02", created="2024-02-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_b{i}", event_type="finished", timestamp="2024-02-09T10:00:00Z", sprint="2024-02", created="2024-02-01"),
            )
        # 2024-03: throughput 3, cycle 8 days (started 03-01, finished 03-09)
        for i in range(3):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_c{i}", event_type="started", timestamp="2024-03-01T10:00:00Z", sprint="2024-03", created="2024-03-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_c{i}", event_type="finished", timestamp="2024-03-09T10:00:00Z", sprint="2024-03", created="2024-03-01"),
            )
        # 2024-04: throughput 8, cycle 7 days (started 04-01, finished 04-08)
        for i in range(8):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_d{i}", event_type="started", timestamp="2024-04-01T10:00:00Z", sprint="2024-04", created="2024-04-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_d{i}", event_type="finished", timestamp="2024-04-08T10:00:00Z", sprint="2024-04", created="2024-04-01"),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-04")
        assert status == 200
        window = body["window"]
        # The biggest improvement is throughput (3 to 8 = 5); the derived
        # cycle_time_minutes is excluded so the same step is not counted twice.
        assert window["biggest_improvement"] == {
            "measure": "throughput",
            "from_sprint": "2024-03",
            "to_sprint": "2024-04",
            "size": 5,
            "unit": "count",
            "precision": "whole",
        }
        # The worst dip is throughput (5 to 3 = 2); no other measure dips.
        assert window["worst_dip"] == {
            "measure": "throughput",
            "from_sprint": "2024-02",
            "to_sprint": "2024-03",
            "size": 2,
            "unit": "count",
            "precision": "whole",
        }
        assert window["too_short"] is False
    finally:
        conn.close()


@requires_db
def test_range_window_standouts_turns():
    """AC2: with throughput 4, 5, 3, 8 and cycle_time_days 9, 8, 8, 7 across
    four sprints, the turns list names exactly (2024-02, throughput) and
    (2024-03, throughput) in window order; cycle_time_days' flat step
    (8 to 8) names no turn."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'so_%'"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: throughput 4, cycle 9 days
        for i in range(4):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_a{i}", event_type="started", timestamp="2024-01-01T10:00:00Z", sprint="2024-01", created="2024-01-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_a{i}", event_type="finished", timestamp="2024-01-10T10:00:00Z", sprint="2024-01", created="2024-01-01"),
            )
        # 2024-02: throughput 5, cycle 8 days
        for i in range(5):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_b{i}", event_type="started", timestamp="2024-02-01T10:00:00Z", sprint="2024-02", created="2024-02-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_b{i}", event_type="finished", timestamp="2024-02-09T10:00:00Z", sprint="2024-02", created="2024-02-01"),
            )
        # 2024-03: throughput 3, cycle 8 days
        for i in range(3):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_c{i}", event_type="started", timestamp="2024-03-01T10:00:00Z", sprint="2024-03", created="2024-03-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_c{i}", event_type="finished", timestamp="2024-03-09T10:00:00Z", sprint="2024-03", created="2024-03-01"),
            )
        # 2024-04: throughput 8, cycle 7 days
        for i in range(8):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_d{i}", event_type="started", timestamp="2024-04-01T10:00:00Z", sprint="2024-04", created="2024-04-01"),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(card_id=f"so_d{i}", event_type="finished", timestamp="2024-04-08T10:00:00Z", sprint="2024-04", created="2024-04-01"),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-04")
        assert status == 200
        # Only throughput changes direction: 4→5 (up), 5→3 (down), 3→8 (up).
        # cycle_time_days: 9→8 (down), 8→8 (flat), 8→7 (down) — no turn.
        assert body["window"]["turns"] == [
            {"sprint": "2024-02", "measure": "throughput"},
            {"sprint": "2024-03", "measure": "throughput"},
        ]
    finally:
        conn.close()


@requires_db
def test_range_window_too_short_two_data_bearing_sprints():
    """AC3: a window with exactly two data-bearing sprints carries too_short
    true, while the per-measure verdict entries are still present."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'so_ts_%'"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card, cycle 4 days
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="so_ts_a", event_type="started", timestamp="2024-01-01T10:00:00Z", sprint="2024-01", created="2024-01-01"),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="so_ts_a", event_type="finished", timestamp="2024-01-05T10:00:00Z", sprint="2024-01", created="2024-01-01"),
        )
        # 2024-02: one card, cycle 2 days
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="so_ts_b", event_type="started", timestamp="2024-02-01T10:00:00Z", sprint="2024-02", created="2024-02-01"),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="so_ts_b", event_type="finished", timestamp="2024-02-03T10:00:00Z", sprint="2024-02", created="2024-02-01"),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        window = body["window"]
        assert window["too_short"] is True
        # Verdict entries are still present (not all null since two data-bearing sprints)
        assert window["verdicts"]["cycle_time_days"] is not None
        # With two data-bearing sprints, turns is empty (needs at least 3)
        assert window["turns"] == []
    finally:
        conn.close()


@requires_db
def test_range_window_zero_data_bearing_sprints_null_standouts():
    """AC4: a window with zero data-bearing sprints has biggest_improvement
    and worst_dip null, turns empty, and too_short true."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'so_zero_%'"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        window = body["window"]
        assert window["biggest_improvement"] is None
        assert window["worst_dip"] is None
        assert window["turns"] == []
        assert window["too_short"] is True
    finally:
        conn.close()
