"""Service tests for the cost answer (story_costs and cost) and the finished event's cost payload at intake."""

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

from sprint_metrics.card import Card
from sprint_metrics.metrics import _compute_cost_summary, _median
from sprint_metrics.service import _start_service
from sprint_metrics.store import init_db


def _cost_card(
    card_id: str,
    model_seconds: int,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_output_tokens: int,
) -> Card:
    """A finished card carrying a full cost payload."""
    return Card(
        created=date(2024, 1, 1),
        model_seconds=model_seconds,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        card_id=card_id,
    )


def test_compute_cost_summary_single_story_six_keys_and_rounded_minutes():
    """AC1: one costed story's item has exactly the four keys, card_id, and
    model_minutes is model_seconds expressed in whole minutes (rounded)."""
    session_costs = {"cost-a": (3500, 4000, 900)}
    story_costs, cost = _compute_cost_summary(session_costs)
    assert len(story_costs) == 1
    item = story_costs[0]
    assert set(item.keys()) == {
        "card_id",
        "model_minutes",
        "input_tokens",
        "output_tokens",
    }
    assert item["card_id"] == "cost-a"
    assert item["model_minutes"] == 58
    assert item["input_tokens"] == 4000
    assert item["output_tokens"] == 900
    assert cost["total"]["model_minutes"] == 58


def test_compute_cost_summary_percents_are_the_sprints_not_the_stories():
    """AC2: every item carries its story's own model minutes and tokens from
    the session records; the percents no longer exist on story_costs items."""
    session_costs = {
        "a": (60, 1000, 800),
        "b": (60, 3000, 3200),
    }
    story_costs, _ = _compute_cost_summary(session_costs)
    for item in story_costs:
        assert "cached_input_percent" not in item
        assert "reasoning_output_percent" not in item


def test_compute_cost_summary_middle_is_median_and_total_is_sum():
    """AC3: cost.middle is the median and cost.total is the sum of the per-story
    values for each measure."""
    session_costs = {
        "c1": (120, 300, 100),
        "c2": (300, 900, 200),
        "c3": (540, 600, 400),
    }
    _, cost = _compute_cost_summary(session_costs)
    assert cost["middle"]["model_minutes"] == 5
    assert cost["total"]["model_minutes"] == 16
    assert cost["middle"]["input_tokens"] == 600
    assert cost["total"]["input_tokens"] == 1800
    assert cost["middle"]["output_tokens"] == 200
    assert cost["total"]["output_tokens"] == 700


def test_compute_cost_summary_cost_object_holds_only_the_three_measures():
    """AC9: cost.middle and cost.total each carry exactly model_minutes,
    input_tokens and output_tokens; no percents ride on cost."""
    session_costs = {
        "c1": (120, 300, 100),
        "c2": (300, 900, 200),
        "c3": (540, 600, 400),
    }
    _, cost = _compute_cost_summary(session_costs)
    measure_keys = {"model_minutes", "input_tokens", "output_tokens"}
    assert set(cost["middle"].keys()) == measure_keys
    assert set(cost["total"].keys()) == measure_keys
    assert cost["middle"] == {"model_minutes": 5, "input_tokens": 600, "output_tokens": 200}
    assert cost["total"] == {"model_minutes": 16, "input_tokens": 1800, "output_tokens": 700}


def test_compute_cost_summary_excludes_stories_without_cost():
    """AC4: a story with no delivery session data is omitted from story_costs,
    and the middle/total are computed from the stories with session data only."""
    session_costs = {"c1": (120, 300, 100)}
    story_costs, cost = _compute_cost_summary(session_costs)
    assert [item["card_id"] for item in story_costs] == ["c1"]
    assert cost["middle"]["model_minutes"] == 2
    assert cost["total"]["model_minutes"] == 2


def test_compute_cost_summary_empty_when_no_story_carries_cost():
    """AC5: when no story carries delivery session data (or there are no
    stories), story_costs is an empty list and cost is None."""
    assert _compute_cost_summary({}) == ([], None)


def test_compute_cost_summary_short_story_rounds_to_whole_minutes():
    """AC10: model_seconds 119 -> model_minutes 2 (119/60 ≈ 1.98 rounded, not
    truncated to 1), so a short story never reads as a free story."""
    session_costs = {"short": (119, 100, 10)}
    story_costs, _ = _compute_cost_summary(session_costs)
    assert story_costs[0]["model_minutes"] == 2


def test_median_odd_even_and_single():
    """The middle value: median for odd counts, the rounded average of the two
    middle values for even counts, the lone value for a single element."""
    assert _median([2, 5, 9]) == 5
    assert _median([58, 59]) == 58
    assert _median([4]) == 4
    assert _median([1, 2, 3, 4]) == round((2 + 3) / 2)


def _stub_range_result(labels):
    """Mimic format_sprint_range_json's per-sprint entries: prior/delta dicts after the first."""
    result = {"sprints": {}}
    for i, label in enumerate(labels):
        entry = {"cycle_time_days": 0, "throughput": 0, "flags": {}}
        if i == 0:
            entry["prior"] = None
            entry["delta"] = None
        else:
            entry["prior"] = {"cycle_time_days": 0}
            entry["delta"] = {"cycle_time_days": 0}
        result["sprints"][label] = entry
    return result


@requires_db
def test_attach_range_cost_entry_carries_cost_and_prior_delta():
    """AC1/AC9: each range entry carries story_costs and cost matching /sprint, and the
    second entry's prior and delta carry the six flat cost names (current minus prior)."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.metrics import _attach_range_cost
    from sprint_metrics.store import upsert_session, upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2026-09', '2026-10')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-09', '2026-10')")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name IN ('2026-09', '2026-10')")
    conn.commit()

    upsert_sprint(conn, "2026-09", date(2026, 9, 1), date(2026, 9, 30), "UTC")
    upsert_sprint(conn, "2026-10", date(2026, 10, 1), date(2026, 10, 31), "UTC")

    # 2026-09: three stories with delivery sessions
    for card_id, model_sec, in_tok, out_tok in [
        ("p1", 1080, 2500, 600),
        ("p2", 1860, 4000, 1200),
        ("p3", 2580, 8000, 3800),
    ]:
        conn.execute(
            """INSERT INTO sprint_metrics.board_events
               (card_id, type, event_time, sprint, card_created)
               VALUES (%s, 'started', %s, '2026-09', '2026-09-01')""",
            (card_id, datetime(2026, 9, 2, 9, 0, tzinfo=UTC)),
        )
        upsert_session(
            conn,
            {
                "card": card_id,
                "role": "Developer",
                "start": "2026-09-02T10:00:00Z",
                "end": "2026-09-02T10:30:00Z",
                "sprint": "2026-09",
                "model_seconds": model_sec,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            },
        )
    # 2026-10: two stories with delivery sessions
    for card_id, model_sec, in_tok, out_tok in [
        ("c1", 3480, 4000, 900),
        ("c2", 5400, 12000, 4800),
    ]:
        conn.execute(
            """INSERT INTO sprint_metrics.board_events
               (card_id, type, event_time, sprint, card_created)
               VALUES (%s, 'started', %s, '2026-10', '2026-10-01')""",
            (card_id, datetime(2026, 10, 2, 9, 0, tzinfo=UTC)),
        )
        upsert_session(
            conn,
            {
                "card": card_id,
                "role": "Developer",
                "start": "2026-10-02T10:00:00Z",
                "end": "2026-10-02T10:30:00Z",
                "sprint": "2026-10",
                "model_seconds": model_sec,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            },
        )
    conn.commit()

    labels = ["2026-09", "2026-10"]
    has_events = {"2026-09", "2026-10"}
    result = _stub_range_result(labels)
    _attach_range_cost(result, conn, labels, has_events)

    e09 = result["sprints"]["2026-09"]
    assert e09["prior"] is None
    assert e09["delta"] is None
    assert e09["cost"]["middle"]["model_minutes"] == 31
    assert e09["cost"]["total"]["model_minutes"] == 92
    assert e09["cost"]["middle"]["input_tokens"] == 4000
    assert e09["cost"]["total"]["input_tokens"] == 14500
    assert e09["cost"]["middle"]["output_tokens"] == 1200
    assert e09["cost"]["total"]["output_tokens"] == 5600
    # story_costs has three entries for 2026-09
    assert len(e09["story_costs"]) == 3

    e10 = result["sprints"]["2026-10"]
    assert e10["cost"]["total"]["model_minutes"] == 148
    assert e10["cost"]["total"]["input_tokens"] == 16000
    assert e10["cost"]["total"]["output_tokens"] == 5700
    assert e10["prior"]["model_minutes_middle"] == 31
    assert e10["prior"]["model_minutes_total"] == 92
    assert e10["prior"]["input_tokens_middle"] == 4000
    assert e10["prior"]["input_tokens_total"] == 14500
    assert e10["prior"]["output_tokens_middle"] == 1200
    assert e10["prior"]["output_tokens_total"] == 5600
    assert e10["delta"]["model_minutes_total"] == 148 - 92
    assert e10["delta"]["input_tokens_total"] == 16000 - 14500
    assert e10["delta"]["output_tokens_total"] == 5700 - 5600
    conn.close()


@requires_db
def test_attach_range_cost_prior_no_costed_stories_nulls_cost():
    """AC2: the preceding sprint has events but no delivery session records,
    so its non-null prior object carries null for the six cost values and the
    delta carries null for each."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.metrics import _attach_range_cost
    from sprint_metrics.store import upsert_session, upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-01', '2024-02')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name IN ('2024-01', '2024-02')")
    conn.commit()

    upsert_sprint(conn, "2024-01", date(2024, 1, 1), date(2024, 1, 31), "UTC")
    upsert_sprint(conn, "2024-02", date(2024, 2, 1), date(2024, 2, 29), "UTC")

    # 2024-01: a started event but no sessions
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('p', 'started', %s, '2024-01', '2024-01-01')""",
        (datetime(2024, 1, 2, 9, 0, tzinfo=UTC),),
    )
    # 2024-02: two stories with delivery sessions
    for card_id, model_sec, in_tok, out_tok in [
        ("c1", 3480, 4000, 900),
        ("c2", 5400, 12000, 4800),
    ]:
        conn.execute(
            """INSERT INTO sprint_metrics.board_events
               (card_id, type, event_time, sprint, card_created)
               VALUES (%s, 'started', %s, '2024-02', '2024-02-01')""",
            (card_id, datetime(2024, 2, 2, 9, 0, tzinfo=UTC)),
        )
        upsert_session(
            conn,
            {
                "card": card_id,
                "role": "Developer",
                "start": "2024-02-02T10:00:00Z",
                "end": "2024-02-02T10:30:00Z",
                "sprint": "2024-02",
                "model_seconds": model_sec,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            },
        )
    conn.commit()

    labels = ["2024-01", "2024-02"]
    has_events = {"2024-01", "2024-02"}
    result = _stub_range_result(labels)
    _attach_range_cost(result, conn, labels, has_events)

    e02 = result["sprints"]["2024-02"]
    assert e02["prior"] is not None
    assert e02["delta"] is not None
    for name in (
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
    ):
        assert e02["prior"][name] is None
        assert e02["delta"][name] is None
    conn.close()


@requires_db
def test_attach_range_cost_null_entry_for_no_events():
    """AC3: a range entry for a sprint with no events is the all-null entry, with
    story_costs an empty array and cost null, alongside the entry's other null metrics."""
    from datetime import datetime

    import psycopg

    from sprint_metrics.metrics import _attach_range_cost
    from sprint_metrics.store import upsert_session, upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2024-01', '2024-02')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name IN ('2024-01', '2024-02')")
    conn.commit()

    upsert_sprint(conn, "2024-01", date(2024, 1, 1), date(2024, 1, 31), "UTC")
    upsert_sprint(conn, "2024-02", date(2024, 2, 1), date(2024, 2, 29), "UTC")

    # 2024-02: one story with a delivery session
    conn.execute(
        """INSERT INTO sprint_metrics.board_events
           (card_id, type, event_time, sprint, card_created)
           VALUES ('c1', 'started', %s, '2024-02', '2024-02-01')""",
        (datetime(2024, 2, 2, 9, 0, tzinfo=UTC),),
    )
    upsert_session(
        conn,
        {
            "card": "c1",
            "role": "Developer",
            "start": "2024-02-02T10:00:00Z",
            "end": "2024-02-02T10:30:00Z",
            "sprint": "2024-02",
            "model_seconds": 3480,
            "input_tokens": 4000,
            "output_tokens": 900,
        },
    )
    conn.commit()

    labels = ["2024-01", "2024-02"]
    has_events = {"2024-02"}  # 2024-01 has no events
    result = _stub_range_result(labels)
    _attach_range_cost(result, conn, labels, has_events)

    e01 = result["sprints"]["2024-01"]
    assert e01["story_costs"] == []
    assert e01["cost"] is None
    assert e01["prior"] is None
    assert e01["delta"] is None
    e02 = result["sprints"]["2024-02"]
    assert e02["story_costs"] is not None
    assert len(e02["story_costs"]) == 1
    assert e02["cost"]["total"]["model_minutes"] == 58
    conn.close()


@requires_db
def test_finite_event_with_full_cost_payload_accepted():
    """AC1: POST a finished event with all five cost fields returns 200."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-a'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # First, post a started event so the card exists
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="cost-a", event_type="started", sprint="2024-01"),
        )
        # Now post a finished event with all five cost fields
        event = _make_event(
            card_id="cost-a",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_partial_cost_payload_rejected():
    """AC2: POST a finished event with only some cost fields returns 400,
    and the error identifies the cost payload as the problem."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-b'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-b",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
            cached_input_tokens=1400,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cost" in body["error"]
    finally:
        conn.close()


@requires_db
def test_negative_cost_field_rejected():
    """AC3a: POST a finished event with a negative cost field returns 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-c'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-c",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
            cached_input_tokens=-5,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cost" in body["error"]
    finally:
        conn.close()


@requires_db
def test_non_integer_cost_field_rejected():
    """AC3b: POST a finished event with a non-integer cost field returns 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-d'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-d",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500.5,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cost" in body["error"]
    finally:
        conn.close()


@requires_db
def test_finite_event_without_cost_fields_accepted():
    """AC4: POST a finished event with no cost fields returns 200, unchanged."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-e'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-e",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_schema_event_cost_properties_declared():
    """AC5: GET /schema/event's card object declares the five cost fields
    as integer properties with minimum 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card_props = body["properties"]["card"]["properties"]
        for field in (
            "model_seconds",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            assert field in card_props
            assert card_props[field]["type"] == "integer"
            assert card_props[field]["minimum"] == 0
    finally:
        conn.close()


@requires_db
def test_partial_cost_error_names_missing_fields():
    """UX7: The 400 response body's error message names the missing cost
    fields by their schema names."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-ux'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-ux",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cached_input_tokens" in body["error"]
        assert "output_tokens" in body["error"]
        assert "reasoning_output_tokens" in body["error"]
    finally:
        conn.close()


@requires_db
def test_schema_event_card_required_unchanged():
    """UX8: The card object's required array is still exactly ['created']."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card = body["properties"]["card"]
        assert card["required"] == ["created"]
    finally:
        conn.close()
