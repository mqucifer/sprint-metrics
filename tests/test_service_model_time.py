"""Service tests for the model-time split at intake and the model_time and model_time_split answers."""

from __future__ import annotations

from datetime import UTC, date

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
def test_finished_event_with_model_time_split_stores_values():
    """AC1: POST a finished event carrying the five cost fields plus a
    model-time split sub-object with refinement 1800 and delivery 3600.
    The response is 200 and the stored row carries the split values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-a'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-a",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=5400,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-a' AND type = 'finished'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (1800, 3600)
    finally:
        conn.close()


@requires_db
def test_partial_model_time_split_rejected():
    """AC2: POST a finished event with a model-time split sub-object carrying
    only one of the two values returns 400, and the error identifies the
    model-time split as sent partially."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-b'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-b",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "model-time split" in body["error"]
        assert "partial" in body["error"]
        assert "delivery" in body["error"]
    finally:
        conn.close()


@requires_db
def test_model_time_split_string_value_rejected():
    """AC3a: POST a finished event with a model-time split value that is a
    string returns 400, and the error names the offending field."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-c'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-c",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": "abc", "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "refinement" in body["error"]
    finally:
        conn.close()


@requires_db
def test_model_time_split_negative_value_rejected():
    """AC3b: POST a finished event with a negative model-time split value
    returns 400, and the error names the offending field."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-d'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-d",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": -1, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "refinement" in body["error"]
    finally:
        conn.close()


@requires_db
def test_finished_event_cost_without_split_stores_null_split():
    """AC4a: POST a finished event with the five cost fields but no split
    sub-object returns 200, api_version stays '1', and the stored row has
    a null split."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-e'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-e",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=5400,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        assert event["api_version"] == "1"
        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-e' AND type = 'finished'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (None, None)
    finally:
        conn.close()


@requires_db
def test_finished_event_split_without_cost_fields_accepted():
    """AC4b: POST a finished event carrying the split sub-object but none of
    the five cost fields is accepted (the split rides under its own
    all-or-nothing rule, separate from the five fields)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-f'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-f",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_started_event_with_split_not_stored():
    """AC5: POST a started event whose card carries a split sub-object
    returns 200 and the split is not stored."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-g'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-g",
            event_type="started",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-g' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (None, None)
    finally:
        conn.close()


@requires_db
def test_resend_finished_event_split_unchanged():
    """AC6: re-sending a stored finished event carrying a split with the same
    card_id, type and timestamp returns 200 and the stored split values are
    unchanged."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-h'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-h",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        # Re-send the same event with different split values
        resend = _make_event(
            card_id="split-h",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 9999, "delivery": 9999},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", resend)
        assert status == 200

        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-h' AND type = 'finished'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (1800, 3600)
    finally:
        conn.close()


@requires_db
def test_schema_event_model_time_split_declared():
    """AC7: GET /schema/event declares the model_time_split sub-object with
    its two fields as required integers with minimum 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card_props = body["properties"]["card"]["properties"]
        assert "model_time_split" in card_props
        split = card_props["model_time_split"]
        assert split["type"] == "object"
        assert split["required"] == ["refinement", "delivery"]
        assert split["properties"]["refinement"] == {"type": "integer", "minimum": 0}
        assert split["properties"]["delivery"] == {"type": "integer", "minimum": 0}
    finally:
        conn.close()


@requires_db
def test_range_model_time_sprint_total_includes_planning_and_cardless():
    """AC3: the sprint's model_time reads the total model minutes and tokens
    across all session records (stories, planning, and card-less sessions).
    Story sessions totalling 15 model minutes (4100 input, 950 output), a
    planning session of 6 model minutes (300 input, 60 output), and a
    card-less session of 4 model minutes (200 input, 40 output) read 25
    model minutes, 4600 input, 1050 output."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.store import upsert_session, upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2025-07'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-07'")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = '2025-07'")
    conn.commit()

    upsert_sprint(conn, "2025-07", date(2025, 7, 1), date(2025, 7, 31), "UTC")

    # Story X: started at 2025-07-05T12:00:00Z, delivery session 840s (14 min)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mx', 'started', %s, '2025-07', '2025-07-01')""",
        (datetime(2025, 7, 5, 12, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "mx",
            "role": "Developer",
            "start": "2025-07-05T12:30:00Z",
            "end": "2025-07-05T13:30:00Z",
            "sprint": "2025-07",
            "model_seconds": 840,
            "input_tokens": 4000,
            "output_tokens": 900,
        },
    )
    # Story Y: started at 2025-07-06T12:00:00Z, delivery session 60s (1 min)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('my', 'started', %s, '2025-07', '2025-07-01')""",
        (datetime(2025, 7, 6, 12, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "my",
            "role": "Developer",
            "start": "2025-07-06T12:30:00Z",
            "end": "2025-07-06T13:30:00Z",
            "sprint": "2025-07",
            "model_seconds": 60,
            "input_tokens": 100,
            "output_tokens": 50,
        },
    )
    # Planning session for story X: 360s (6 min), before the story's start
    upsert_session(
        conn,
        {
            "card": "mx",
            "role": "Developer",
            "start": "2025-07-05T10:00:00Z",
            "end": "2025-07-05T11:00:00Z",
            "sprint": "2025-07",
            "model_seconds": 360,
            "input_tokens": 300,
            "output_tokens": 60,
        },
    )
    # Card-less session: 240s (4 min)
    upsert_session(
        conn,
        {
            "card": None,
            "role": "Developer",
            "start": "2025-07-07T10:00:00Z",
            "end": "2025-07-07T11:00:00Z",
            "sprint": "2025-07",
            "model_seconds": 240,
            "input_tokens": 200,
            "output_tokens": 40,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        status, body = _get_json(f"{base}/range?start=2025-07&end=2025-07")
        assert status == 200
        entry = body["sprints"]["2025-07"]
        # Story delivery: 840+60=900s (15 min), 4100 in, 950 out
        # Planning: 360s (6 min), 300 in, 60 out
        # Card-less: 240s (4 min), 200 in, 40 out
        # Total: 1500s (25 min), 4600 in, 1050 out
        assert entry["model_time"] == {
            "model_minutes": 25,
            "input_tokens": 4600,
            "output_tokens": 1050,
        }
    finally:
        conn.close()


@requires_db
def test_range_model_time_split_summed_whole_minutes():
    """AC1: a sprint whose stories carry sessions split into planning and
    delivery has its model_time_split answer carry the whole-minute totals,
    each part converted to whole minutes and summed: planning 30 and
    delivery 70 for a story split 1200 s / 3600 s and a story split
    600 s / 600 s."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.store import upsert_session

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-09'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('mts1', 'mts2')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-09'")
    conn.commit()

    # Story mts1: started at 2024-09-05T12:00:00Z
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts1', 'started', %s, '2024-09', '2024-09-01')""",
        (datetime(2024, 9, 5, 12, 0, tzinfo=UTC),),
    )
    # Planning session: 1200 model seconds (before start)
    upsert_session(
        conn,
        {
            "card": "mts1",
            "role": "Developer",
            "start": "2024-09-05T10:00:00Z",
            "end": "2024-09-05T11:00:00Z",
            "sprint": "2024-09",
            "model_seconds": 1200,
            "input_tokens": 2000,
            "output_tokens": 500,
        },
    )
    # Delivery session: 3600 model seconds (after start)
    upsert_session(
        conn,
        {
            "card": "mts1",
            "role": "Developer",
            "start": "2024-09-05T12:30:00Z",
            "end": "2024-09-05T13:30:00Z",
            "sprint": "2024-09",
            "model_seconds": 3600,
            "input_tokens": 2000,
            "output_tokens": 400,
        },
    )
    # Story mts2: started at 2024-09-06T12:00:00Z
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts2', 'started', %s, '2024-09', '2024-09-01')""",
        (datetime(2024, 9, 6, 12, 0, tzinfo=UTC),),
    )
    # Planning session: 600 model seconds (before start)
    upsert_session(
        conn,
        {
            "card": "mts2",
            "role": "Developer",
            "start": "2024-09-06T10:00:00Z",
            "end": "2024-09-06T11:00:00Z",
            "sprint": "2024-09",
            "model_seconds": 600,
            "input_tokens": 1000,
            "output_tokens": 250,
        },
    )
    # Delivery session: 600 model seconds (after start)
    upsert_session(
        conn,
        {
            "card": "mts2",
            "role": "Developer",
            "start": "2024-09-06T12:30:00Z",
            "end": "2024-09-06T13:30:00Z",
            "sprint": "2024-09",
            "model_seconds": 600,
            "input_tokens": 1000,
            "output_tokens": 250,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        status, body = _get_json(f"{base}/range?start=2024-09&end=2024-09")
        assert status == 200
        entry = body["sprints"]["2024-09"]
        assert entry["model_time_split"] == {"planning": 30, "delivery": 70}
    finally:
        conn.close()


@requires_db
def test_range_model_time_split_null_when_costed_but_no_split():
    """AC2: a sprint whose costed stories carry the five-field cost payload but
    no session records has its model_time_split answer null —
    no data, not zero."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-10'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'mts3'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-10'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="mts3",
                event_type="finished",
                timestamp="2024-10-05T12:00:00Z",
                sprint="2024-10",
                model_seconds=4800,
                input_tokens=4000,
                cached_input_tokens=1400,
                output_tokens=900,
                reasoning_output_tokens=300,
            ),
        )
        status, body = _get_json(f"{base}/range?start=2024-10&end=2024-10")
        assert status == 200
        entry = body["sprints"]["2024-10"]
        assert entry["cost"] is None
        assert entry["model_time_split"] is None
    finally:
        conn.close()


@requires_db
def test_range_model_time_split_null_when_no_costed_stories():
    """AC3: a sprint with no costed stories at all has its model_time_split
    answer null, alongside the entry's null cost."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint = '2024-11'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'mts4'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-11'")
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="mts4",
                event_type="started",
                timestamp="2024-11-05T09:00:00Z",
                sprint="2024-11",
            ),
        )
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="mts4",
                event_type="finished",
                timestamp="2024-11-05T12:00:00Z",
                sprint="2024-11",
            ),
        )
        status, body = _get_json(f"{base}/range?start=2024-11&end=2024-11")
        assert status == 200
        entry = body["sprints"]["2024-11"]
        assert entry["cost"] is None
        assert entry["model_time_split"] is None
    finally:
        conn.close()


@requires_db
def test_trend_model_time_split_refinement_and_delivery():
    """AC4: GET /trend?metric=model_time_split_refinement_minutes and
    model_time_split_delivery_minutes return the per-sprint whole minutes
    (null where no story carries session data)."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.store import upsert_session

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-05', '2024-06')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('mts5', 'mts6', 'mts7')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-05', '2024-06')")
    conn.commit()

    # 2024-05: two stories with sessions (planning + delivery)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts5', 'started', %s, '2024-05', '2024-05-01')""",
        (datetime(2024, 5, 5, 12, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "mts5",
            "role": "Developer",
            "start": "2024-05-05T10:00:00Z",
            "end": "2024-05-05T11:00:00Z",
            "sprint": "2024-05",
            "model_seconds": 1200,
            "input_tokens": 2000,
            "output_tokens": 500,
        },
    )
    upsert_session(
        conn,
        {
            "card": "mts5",
            "role": "Developer",
            "start": "2024-05-05T12:30:00Z",
            "end": "2024-05-05T13:30:00Z",
            "sprint": "2024-05",
            "model_seconds": 3600,
            "input_tokens": 2000,
            "output_tokens": 400,
        },
    )
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts6', 'started', %s, '2024-05', '2024-05-01')""",
        (datetime(2024, 5, 6, 12, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "mts6",
            "role": "Developer",
            "start": "2024-05-06T10:00:00Z",
            "end": "2024-05-06T11:00:00Z",
            "sprint": "2024-05",
            "model_seconds": 600,
            "input_tokens": 1000,
            "output_tokens": 250,
        },
    )
    upsert_session(
        conn,
        {
            "card": "mts6",
            "role": "Developer",
            "start": "2024-05-06T12:30:00Z",
            "end": "2024-05-06T13:30:00Z",
            "sprint": "2024-05",
            "model_seconds": 600,
            "input_tokens": 1000,
            "output_tokens": 250,
        },
    )
    # 2024-06: a story with no sessions (no data)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts7', 'started', %s, '2024-06', '2024-06-01')""",
        (datetime(2024, 6, 5, 12, 0, tzinfo=UTC),),
    )
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        status, body = _get_json(
            f"{base}/trend?metric=model_time_split_refinement_minutes&start=2024-05&end=2024-06"
        )
        assert status == 200
        assert body["metric"] == "model_time_split_refinement_minutes"
        assert body["values"] == [
            {"sprint": "2024-05", "value": 30},
            {"sprint": "2024-06", "value": None},
        ]

        status, body = _get_json(
            f"{base}/trend?metric=model_time_split_delivery_minutes&start=2024-05&end=2024-06"
        )
        assert status == 200
        assert body["metric"] == "model_time_split_delivery_minutes"
        assert body["values"] == [
            {"sprint": "2024-05", "value": 70},
            {"sprint": "2024-06", "value": None},
        ]
    finally:
        conn.close()


@requires_db
def test_range_model_time_split_prior_and_delta():
    """AC5: the flat split names appear in each later entry's prior and delta
    (null where a sprint has no split data)."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.store import upsert_session

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2025-03', '2025-04', '2025-05')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('mts8', 'mts9', 'mts10')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2025-03', '2025-04', '2025-05')"
    )
    conn.commit()

    # 2025-03: split 600 s / 1200 s -> planning 10 / delivery 20 minutes
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts8', 'started', %s, '2025-03', '2025-03-01')""",
        (datetime(2025, 3, 5, 12, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "mts8",
            "role": "Developer",
            "start": "2025-03-05T10:00:00Z",
            "end": "2025-03-05T11:00:00Z",
            "sprint": "2025-03",
            "model_seconds": 600,
            "input_tokens": 2000,
            "output_tokens": 500,
        },
    )
    upsert_session(
        conn,
        {
            "card": "mts8",
            "role": "Developer",
            "start": "2025-03-05T12:30:00Z",
            "end": "2025-03-05T13:30:00Z",
            "sprint": "2025-03",
            "model_seconds": 1200,
            "input_tokens": 2000,
            "output_tokens": 400,
        },
    )
    # 2025-04: a started event but no sessions (no data)
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts9', 'started', %s, '2025-04', '2025-04-01')""",
        (datetime(2025, 4, 5, 12, 0, tzinfo=UTC),),
    )
    # 2025-05: split 1200 s / 600 s -> planning 20 / delivery 10 minutes
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('mts10', 'started', %s, '2025-05', '2025-05-01')""",
        (datetime(2025, 5, 5, 12, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "mts10",
            "role": "Developer",
            "start": "2025-05-05T10:00:00Z",
            "end": "2025-05-05T11:00:00Z",
            "sprint": "2025-05",
            "model_seconds": 1200,
            "input_tokens": 2000,
            "output_tokens": 500,
        },
    )
    upsert_session(
        conn,
        {
            "card": "mts10",
            "role": "Developer",
            "start": "2025-05-05T12:30:00Z",
            "end": "2025-05-05T13:30:00Z",
            "sprint": "2025-05",
            "model_seconds": 600,
            "input_tokens": 2000,
            "output_tokens": 400,
        },
    )
    conn.commit()

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        status, body = _get_json(f"{base}/range?start=2025-03&end=2025-05")
        assert status == 200
        e1 = body["sprints"]["2025-03"]
        e2 = body["sprints"]["2025-04"]
        e3 = body["sprints"]["2025-05"]
        assert e1["model_time_split"] == {"planning": 10, "delivery": 20}
        assert e2["model_time_split"] is None
        assert e3["model_time_split"] == {"planning": 20, "delivery": 10}
        assert e1["prior"] is None
        assert e1["delta"] is None
        # 2025-04's prior reads 2025-03's split; its delta is null (no data).
        assert e2["prior"]["model_time_split_refinement_minutes"] == 10
        assert e2["prior"]["model_time_split_delivery_minutes"] == 20
        assert e2["delta"]["model_time_split_refinement_minutes"] is None
        assert e2["delta"]["model_time_split_delivery_minutes"] is None
        # 2025-05's prior reads 2025-04's nulls; its delta is null too.
        assert e3["prior"]["model_time_split_refinement_minutes"] is None
        assert e3["prior"]["model_time_split_delivery_minutes"] is None
        assert e3["delta"]["model_time_split_refinement_minutes"] is None
        assert e3["delta"]["model_time_split_delivery_minutes"] is None
    finally:
        conn.close()


def test_sprint_range_schema_declares_model_time_split_on_sprint_entry():
    """AC5: SPRINT_RANGE_SCHEMA declares model_time_split as an optional
    property of a sprint entry (not in required), with planning and delivery
    (integer); the flat split names appear in each later entry's prior and
    delta (integer or null)."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    assert "model_time_split" not in sprint_entry["required"]
    split = sprint_entry["properties"]["model_time_split"]
    assert split["type"] == ["object", "null"]
    assert split["required"] == ["planning", "delivery"]
    assert split["properties"]["planning"] == {"type": "integer"}
    assert split["properties"]["delivery"] == {"type": "integer"}
    for which in ("prior", "delta"):
        flat = sprint_entry["properties"][which]["properties"]
        assert flat["model_time_split_refinement_minutes"] == {"type": ["integer", "null"]}
        assert flat["model_time_split_delivery_minutes"] == {"type": ["integer", "null"]}
