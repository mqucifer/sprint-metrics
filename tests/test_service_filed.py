"""Service tests for the filed event, the filed answer on /range, and self_filed_share_percent on /trend."""

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
def test_post_filed_stores_filer_opener_and_project():
    """AC1: POST /events with type='filed' carrying filer, opener, and project
    answers 200 and the stored filed row carries all three values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'f1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "f1",
            "type": "filed",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "filer": "crew",
            "opener": "qa-suite test failed",
            "project": "qa-suite",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT filer, opener, project FROM sprint_metrics.board_events "
            "WHERE card_id = 'f1' AND type = 'filed'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "crew"
        assert rows[0][1] == "qa-suite test failed"
        assert rows[0][2] == "qa-suite"
    finally:
        conn.close()


@requires_db
def test_post_filed_without_optional_fields_stores_null():
    """AC2: POST /events with type='filed' and no filer, opener, or project
    answers 200 and stores those columns as NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'f2'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "f2",
            "type": "filed",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT filer, opener, project FROM sprint_metrics.board_events "
            "WHERE card_id = 'f2' AND type = 'filed'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
        assert rows[0][1] is None
        assert rows[0][2] is None
    finally:
        conn.close()


@requires_db
def test_post_filed_resend_fills_null_keeps_existing():
    """AC3: re-sending a stored 'filed' event with an opener the first send
    left NULL answers 200; the NULL field takes the supplied value and fields
    that already hold a value are not changed."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'f3'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        first = {
            "api_version": "1",
            "card_id": "f3",
            "type": "filed",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "filer": "crew",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", first)
        assert status == 200
        assert "error" not in body

        resend = {
            "api_version": "1",
            "card_id": "f3",
            "type": "filed",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "opener": "split from card 42",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", resend)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT filer, opener, project FROM sprint_metrics.board_events "
            "WHERE card_id = 'f3' AND type = 'filed'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "crew"
        assert rows[0][1] == "split from card 42"
        assert rows[0][2] is None
    finally:
        conn.close()


@requires_db
def test_filed_event_does_not_change_range_or_trend():
    """AC6: POSTing a 'filed' event for a sprint that already carries started and
    finished events does not change the /range or /trend responses."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-06'")
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"

    events = [
        {
            "api_version": "1",
            "card_id": "f6a",
            "type": "started",
            "sprint": "2024-06",
            "timestamp": "2024-06-02T09:00:00Z",
            "card": {"created": "2024-06-01"},
        },
        {
            "api_version": "1",
            "card_id": "f6a",
            "type": "finished",
            "sprint": "2024-06",
            "timestamp": "2024-06-10T15:00:00Z",
            "card": {"created": "2024-06-01"},
        },
    ]
    for ev in events:
        status, _ = _post_events(f"{base_url}/events", ev)
        assert status == 200

    status, before = _get_json(f"{base_url}/range?start=2024-06&end=2024-06")
    assert status == 200

    status, trend_before = _get_json(f"{base_url}/trend?metric=throughput&start=2024-06&end=2024-06")
    assert status == 200

    filed_event = {
        "api_version": "1",
        "card_id": "f6a",
        "type": "filed",
        "sprint": "2024-06",
        "timestamp": "2024-06-01T08:00:00Z",
        "card": {"created": "2024-06-01"},
        "filer": "crew",
        "opener": "qa-suite test failed",
        "project": "qa-suite",
    }
    status, _ = _post_events(f"{base_url}/events", filed_event)
    assert status == 200

    status, after = _get_json(f"{base_url}/range?start=2024-06&end=2024-06")
    assert status == 200
    # The filed event adds a 'filed' section to the range entry; all other
    # delivery measures are unchanged.
    before_sprint = before["sprints"]["2024-06"]
    after_sprint = after["sprints"]["2024-06"]
    assert before_sprint.get("filed") is None
    assert after_sprint["filed"] is not None
    assert after_sprint["filed"]["crew_total"] == 1
    assert after_sprint["filed"]["unknown"] == 1
    # The other measures are unchanged
    before_without_filed = {k: v for k, v in before_sprint.items() if k != "filed"}
    after_without_filed = {k: v for k, v in after_sprint.items() if k != "filed"}
    assert after_without_filed == before_without_filed

    status, trend_after = _get_json(f"{base_url}/trend?metric=throughput&start=2024-06&end=2024-06")
    assert status == 200
    assert trend_after == trend_before

    conn.close()


@requires_db
def test_query_filed_events_returns_stored_facts():
    """AC7: query_filed_events returns each 'filed' row's card_id together with its
    filer, opener, and project, in event order, with NULL for a fact the crew
    did not send."""
    import psycopg

    from sprint_metrics.store import query_filed_events

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-07'")
    conn.commit()

    events = [
        {
            "api_version": "1",
            "card_id": "f7a",
            "type": "filed",
            "sprint": "2024-07",
            "timestamp": "2024-07-01T08:00:00Z",
            "card": {"created": "2024-07-01"},
            "filer": "crew",
            "opener": "qa-suite test failed",
            "project": "qa-suite",
        },
        {
            "api_version": "1",
            "card_id": "f7b",
            "type": "filed",
            "sprint": "2024-07",
            "timestamp": "2024-07-02T09:00:00Z",
            "card": {"created": "2024-07-02"},
            "filer": "sponsor",
        },
    ]
    port = _start_service(conn, 0)
    try:
        for ev in events:
            status, _ = _post_events(f"http://127.0.0.1:{port}/events", ev)
            assert status == 200
    finally:
        conn.close()

    conn2 = psycopg.connect(SPRINT_METRICS_DB)
    result = query_filed_events(conn2, "2024-07")
    assert result == [
        ("f7a", "crew", "qa-suite test failed", "qa-suite"),
        ("f7b", "sponsor", None, None),
    ]
    conn2.close()


@requires_db
def test_trend_self_filed_share_percent_two_sprints():
    """AC1/AC2: GET /trend?metric=self_filed_share_percent reports the whole
    percent (the crew-filed total over the sprint's total cards) for a sprint
    that carries filing facts, and null for a sprint that carries none — a
    value of 0 or 100 is never produced for a sprint without facts."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        # 2024-01: one crew-filed card and one Sponsor-filed card — crew filed 1 of 2.
        _post_events(
            f"{base_url}/events",
            {
                "api_version": "1",
                "card_id": "sfsa",
                "type": "filed",
                "sprint": "2024-01",
                "timestamp": "2024-01-02T08:00:00Z",
                "card": {"created": "2024-01-01"},
                "filer": "crew",
                "opener": "found",
            },
        )
        _post_events(
            f"{base_url}/events",
            {
                "api_version": "1",
                "card_id": "sfsb",
                "type": "filed",
                "sprint": "2024-01",
                "timestamp": "2024-01-03T08:00:00Z",
                "card": {"created": "2024-01-01"},
                "filer": "sponsor",
            },
        )
        # 2024-02: a card that started and finished, but no filing facts.
        _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="sfsc",
                event_type="started",
                timestamp="2024-02-02T08:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="sfsc",
                event_type="finished",
                timestamp="2024-02-05T08:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["metric"] == "self_filed_share_percent"
        assert len(body["values"]) == 2
        # 2024-01 carries filing facts: crew filed 1 of 2 cards -> round(1/2*100) = 50.
        assert body["values"][0] == {"sprint": "2024-01", "value": 50}
        assert isinstance(body["values"][0]["value"], int)
        # 2024-02 carries no filing facts: null, never 0 or 100.
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
    finally:
        conn.close()


def test_schema_event_filed_fields_declared():
    """AC8: the event-intake schema declares 'filed' as the ninth accepted type
    and filer, opener, project as optional string fields, both at GET /schema/event
    and in the committed schemas/event-intake.json."""
    import json
    from pathlib import Path

    from sprint_metrics.schema import EVENT_INTAKE_SCHEMA

    # Check the in-code schema.
    type_enum = EVENT_INTAKE_SCHEMA["properties"]["type"]["enum"]
    assert "filed" in type_enum
    assert len(type_enum) == 10
    for field in ("filer", "opener", "project"):
        assert EVENT_INTAKE_SCHEMA["properties"][field] == {"type": "string"}
        assert field not in EVENT_INTAKE_SCHEMA["required"]

    # Check the committed JSON file matches.
    committed = json.loads((Path(__file__).parent.parent / "schemas" / "event-intake.json").read_text())
    assert committed == EVENT_INTAKE_SCHEMA


def test_service_md_post_events_lists_filed():
    """AC9: docs/service.md's generated endpoints table names 'filed' alongside
    the eight existing types in the POST /events row."""
    from pathlib import Path

    text = (Path(__file__).parent.parent / "docs" / "service.md").read_text()
    section = text.split("BEGIN:service")[1].split("END:service")[0]
    post_events_row = [line for line in section.splitlines() if "/events" in line][0]
    assert "filed" in post_events_row
    for existing_type in (
        "started",
        "blocked",
        "unblocked",
        "finished",
        "escalated",
        "attempt_failed",
        "superseded",
        "returned",
    ):
        assert existing_type in post_events_row


@requires_db
def test_range_filed_reports_worked_example():
    """AC1: a /range for the Goal's worked example sprint — 25 of 27 self-filed:
    10 found, 12 from-process, 3 split, 0 unknown; one each by the Sponsor and the
    operator; none by anyone else — reports the filed split: the crew-filed total
    (25) with its found/from-process/split/unknown counts, the Sponsor (1),
    operator (1) and other (0) counts, the sprint's total cards (27), and the
    self-filed share (93 percent) with its numerator (25) and denominator (27)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-05'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        def filed(card_id, filer, opener=None):
            ev = {
                "api_version": "1",
                "card_id": card_id,
                "type": "filed",
                "sprint": "2024-05",
                "timestamp": "2024-05-01T08:00:00Z",
                "card": {"created": "2024-05-01"},
                "filer": filer,
            }
            if opener is not None:
                ev["opener"] = opener
            return ev

        events = (
            [filed(f"wx_f_{i}", "crew", "found") for i in range(10)]
            + [filed(f"wx_p_{i}", "crew", "process") for i in range(12)]
            + [filed(f"wx_s_{i}", "crew", "split") for i in range(3)]
            + [filed("wx_sponsor", "sponsor")]
            + [filed("wx_operator", "operator")]
        )
        for ev in events:
            status, _ = _post_events(f"http://127.0.0.1:{port}/events", ev)
            assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-05&end=2024-05")
        assert status == 200
        section = body["sprints"]["2024-05"]["filed"]
        assert section["crew_total"] == 25
        assert section["found"] == 10
        assert section["from_process"] == 12
        assert section["split"] == 3
        assert section["unknown"] == 0
        assert section["sponsor"] == 1
        assert section["operator"] == 1
        assert section["other"] == 0
        assert section["total_cards"] == 27
        assert section["self_filed_share"] == {"percent": 93, "numerator": 25, "denominator": 27}
    finally:
        conn.close()


@requires_db
def test_range_filed_distinguishes_null_from_zero_crew():
    """AC2: a sprint that carries events but no filing facts reads filed null (no
    data, not zero); a sprint whose filing facts name only non-crew filers reads the
    zero crew counts — the two are distinct in the answer."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-02', '2024-03')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-02: events (started + finished) but no filed events.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="wxnull_a",
                event_type="started",
                timestamp="2024-02-02T09:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="wxnull_a",
                event_type="finished",
                timestamp="2024-02-06T09:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        # 2024-03: filed events, all by non-crew filers (the crew filed nothing).
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "wxzero_sponsor",
                "type": "filed",
                "sprint": "2024-03",
                "timestamp": "2024-03-01T08:00:00Z",
                "card": {"created": "2024-03-01"},
                "filer": "sponsor",
            },
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "wxzero_operator",
                "type": "filed",
                "sprint": "2024-03",
                "timestamp": "2024-03-01T08:05:00Z",
                "card": {"created": "2024-03-01"},
                "filer": "operator",
            },
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-02&end=2024-03")
        assert status == 200
        sprints = body["sprints"]
        # Events but no filing facts: no data, not a zero split.
        assert sprints["2024-02"]["filed"] is None
        # Filing facts in which the crew filed nothing: the zero crew counts.
        zero = sprints["2024-03"]["filed"]
        assert zero is not None
        assert zero["crew_total"] == 0
        assert zero["found"] == 0
        assert zero["from_process"] == 0
        assert zero["split"] == 0
        assert zero["unknown"] == 0
        assert zero["sponsor"] == 1
        assert zero["operator"] == 1
        assert zero["other"] == 0
        assert zero["total_cards"] == 2
    finally:
        conn.close()


@requires_db
def test_range_filed_null_for_sprint_with_no_events():
    """AC3: a /range spanning sprints where one has no events at all reads filed
    null for that sprint, exactly like its other answers — no data."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-04', '2024-06')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-04: one completed card; 2024-06: nothing at all.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="wxnoev_done",
                event_type="started",
                timestamp="2024-04-03T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="wxnoev_done",
                event_type="finished",
                timestamp="2024-04-07T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-04&end=2024-06")
        assert status == 200
        sprints = body["sprints"]
        # The no-event sprint reads filed null, exactly like its other answers.
        assert sprints["2024-06"]["filed"] is None
        assert sprints["2024-06"]["throughput"] is None
        # The event-bearing sprint with no filing facts also reads filed null.
        assert sprints["2024-04"]["filed"] is None
        assert sprints["2024-04"]["throughput"] == 1
    finally:
        conn.close()


def _filed_event(card_id: str, sprint: str, filer: str | None = None, opener: str | None = None) -> dict:
    """Build a 'filed' event for the sprint; the fact fields are omitted when not given."""
    event = {
        "api_version": "1",
        "card_id": card_id,
        "type": "filed",
        "sprint": sprint,
        "timestamp": f"{sprint}-02T08:00:00Z",
        "card": {"created": f"{sprint}-01"},
    }
    if filer is not None:
        event["filer"] = filer
    if opener is not None:
        event["opener"] = opener
    return event


@requires_db
def test_trend_self_filed_share_three_sprints_chronological():
    """AC1: GET /trend with self_filed_share_percent over a three-sprint window
    answers 200 in the /trend response shape — api_version, a metric field
    naming the measure, start, end, and a values array — carrying exactly one
    entry per sprint label in the window, in chronological order, each value a
    whole percent (a JSON integer, not a string or a fraction): 2024-01 holds
    10 filed cards, all 10 by the crew (100); 2024-02, 20 filed, 15 by the
    crew (75); 2024-03, 40 filed, 8 by the crew (20)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02', '2024-03')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        # 2024-01: 10 cards filed, 10 by the crew.
        for i in range(10):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tsa_{i}", "2024-01", "crew", "found")
            )
            assert status == 200
        # 2024-02: 20 cards filed, 15 by the crew, 5 by the Sponsor.
        for i in range(15):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tsb_{i}", "2024-02", "crew", "process")
            )
            assert status == 200
        for i in range(5):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tsbs_{i}", "2024-02", "sponsor")
            )
            assert status == 200
        # 2024-03: 40 cards filed, 8 by the crew, 32 by the operator.
        for i in range(8):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tsc_{i}", "2024-03", "crew", "split")
            )
            assert status == 200
        for i in range(32):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tscs_{i}", "2024-03", "operator")
            )
            assert status == 200

        status, body = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-03"
        )
        assert status == 200
        # The /trend response shape: api_version, metric, start, end, values.
        assert set(body) == {"api_version", "metric", "start", "end", "values"}
        assert body["metric"] == "self_filed_share_percent"
        assert body["start"] == "2024-01"
        assert body["end"] == "2024-03"
        assert isinstance(body["api_version"], str)
        # One entry per sprint label in the window, in chronological order.
        assert [entry["sprint"] for entry in body["values"]] == ["2024-01", "2024-02", "2024-03"]
        assert body["values"][0]["value"] == 100
        assert body["values"][1]["value"] == 75
        assert body["values"][2]["value"] == 20
        # Each value is a whole percent: a JSON integer, not a string or a fraction.
        for entry in body["values"]:
            assert isinstance(entry["value"], int)
            assert not isinstance(entry["value"], bool)
    finally:
        conn.close()


@requires_db
def test_trend_self_filed_share_matches_range_filed_split():
    """AC2: over the same window, each sprint's /trend self-filed share value
    equals the share derived from that sprint's /range filed split — the total
    the crew filed, of the total cards filed — so the cross-sprint trend and
    the per-sprint section, computed from the same stored facts, can never
    disagree."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02', '2024-03')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        # The same stored history as the three-sprint window: 10 of 10, 15 of 20, 8 of 40.
        for i in range(10):
            _post_events(f"{base_url}/events", _filed_event(f"tm1_{i}", "2024-01", "crew", "found"))
        for i in range(15):
            _post_events(f"{base_url}/events", _filed_event(f"tm2_{i}", "2024-02", "crew", "process"))
        for i in range(5):
            _post_events(f"{base_url}/events", _filed_event(f"tm2s_{i}", "2024-02", "sponsor"))
        for i in range(8):
            _post_events(f"{base_url}/events", _filed_event(f"tm3_{i}", "2024-03", "crew", "split"))
        for i in range(32):
            _post_events(f"{base_url}/events", _filed_event(f"tm3s_{i}", "2024-03", "operator"))

        trend_status, trend = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-03"
        )
        assert trend_status == 200
        range_status, rng = _get_json(f"{base_url}/range?start=2024-01&end=2024-03")
        assert range_status == 200

        expected = {"2024-01": (10, 10), "2024-02": (15, 20), "2024-03": (8, 40)}
        for entry in trend["values"]:
            label = entry["sprint"]
            split = rng["sprints"][label]["filed"]
            assert split is not None
            crew_total, total = expected[label]
            # The /range split's counts agree with the stored history.
            assert split["crew_total"] == crew_total
            assert split["total_cards"] == total
            # The /trend value is the share derived from those same counts.
            assert entry["value"] == split["self_filed_share"]["percent"]
            assert entry["value"] == round(crew_total / total * 100)
        assert [entry["value"] for entry in trend["values"]] == [100, 75, 20]
    finally:
        conn.close()


@requires_db
def test_trend_self_filed_share_counts_card_in_filed_sprint_not_merge_sprint():
    """AC3: a card whose 'filed' event names sprint 2024-01 and whose finished
    event is in sprint 2024-02 (filed in 2024-01, merged in 2024-02) counts,
    in the self-filed share, in the sprint named on its 'filed' event — 2024-01
    holds 5 filed cards, 4 of them by the crew including this card (80), and
    2024-02 holds 5 filed, 1 by the crew, not this card (20). The delivery
    measure (throughput) counts the card in 2024-02, where it merges; the
    filed share's values differ from the delivery measures' merge-sprint
    attribution by design."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        # Card txa: filed in 2024-01 by the crew, merged in 2024-02.
        status, _ = _post_events(f"{base_url}/events", _filed_event("txa", "2024-01", "crew", "found"))
        assert status == 200
        status, _ = _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="txa",
                event_type="started",
                timestamp="2024-01-05T08:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        assert status == 200
        status, _ = _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="txa",
                event_type="finished",
                timestamp="2024-02-05T08:00:00Z",
                sprint="2024-02",
                created="2024-01-01",
            ),
        )
        assert status == 200
        # 2024-01: 5 cards filed, 4 by the crew (three more, plus card txa).
        for i in range(3):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"txa_c{i}", "2024-01", "crew", "found")
            )
            assert status == 200
        status, _ = _post_events(f"{base_url}/events", _filed_event("txa_sp", "2024-01", "sponsor"))
        assert status == 200
        # 2024-02: 5 cards filed, 1 by the crew (not card txa).
        status, _ = _post_events(f"{base_url}/events", _filed_event("txa_cw", "2024-02", "crew", "process"))
        assert status == 200
        for i in range(4):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"txa_o{i}", "2024-02", "operator")
            )
            assert status == 200

        status, share = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-02"
        )
        assert status == 200
        # The card counts in the sprint named on its 'filed' event.
        assert share["values"] == [
            {"sprint": "2024-01", "value": 80},
            {"sprint": "2024-02", "value": 20},
        ]
        # The delivery measure counts the card where it merges.
        status, throughput = _get_json(f"{base_url}/trend?metric=throughput&start=2024-01&end=2024-02")
        assert status == 200
        assert throughput["values"] == [
            {"sprint": "2024-01", "value": 0},
            {"sprint": "2024-02", "value": 1},
        ]
    finally:
        conn.close()


@requires_db
def test_trend_self_filed_share_null_where_no_filing_facts():
    """AC4: a sprint with events but no filing facts reads null (no data),
    never 0 and never 100 — whether it has no 'filed' events at all, or
    'filed' events whose filing-fact fields are all absent. 2024-01's stored
    filing facts show 5 cards filed, 4 by the crew (80); 2024-02 holds started
    and finished rows but no filing facts (null); 2024-03 holds 'filed' events
    whose filing-fact fields are all absent (null)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02', '2024-03')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        # 2024-01: 5 cards filed, 4 by the crew.
        for i in range(4):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tnull_{i}", "2024-01", "crew", "found")
            )
            assert status == 200
        status, _ = _post_events(f"{base_url}/events", _filed_event("tnull_sp", "2024-01", "sponsor"))
        assert status == 200
        # 2024-02: started and finished rows, no 'filed' events at all.
        status, _ = _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="tnull_card",
                event_type="started",
                timestamp="2024-02-02T08:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        assert status == 200
        status, _ = _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="tnull_card",
                event_type="finished",
                timestamp="2024-02-05T08:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        assert status == 200
        # 2024-03: 'filed' events whose filing-fact fields are all absent.
        for i in range(2):
            status, _ = _post_events(f"{base_url}/events", _filed_event(f"tnull_f{i}", "2024-03"))
            assert status == 200

        status, body = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-03"
        )
        assert status == 200
        # Filing facts present: the share; no facts (either flavour): null.
        assert body["values"] == [
            {"sprint": "2024-01", "value": 80},
            {"sprint": "2024-02", "value": None},
            {"sprint": "2024-03", "value": None},
        ]
    finally:
        conn.close()


@requires_db
def test_trend_self_filed_share_zero_when_crew_filed_nothing():
    """AC5: a sprint whose stored filing facts show the crew filed none of the
    sprint's cards reads 0 — a true zero, distinct from the null of a
    fact-less sprint. 2024-01's filing facts show 6 cards filed: 2 by the
    Sponsor, 1 by the operator, 3 by someone else — none by the crew."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        for i in range(2):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tzero_sp{i}", "2024-01", "sponsor")
            )
            assert status == 200
        status, _ = _post_events(
            f"{base_url}/events", _filed_event("tzero_op", "2024-01", "operator")
        )
        assert status == 200
        for i in range(3):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tzero_ot{i}", "2024-01", "other")
            )
            assert status == 200
        # 2024-02: no events at all — it reads null, the fact-less answer.
        status, body = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-02"
        )
        assert status == 200
        # The facts are present and show the crew filed none: a true zero.
        assert body["values"] == [
            {"sprint": "2024-01", "value": 0},
            {"sprint": "2024-02", "value": None},
        ]
        zero = body["values"][0]["value"]
        assert zero == 0
        assert isinstance(zero, int)
        assert not isinstance(zero, bool)
    finally:
        conn.close()


@requires_db
def test_trend_self_filed_share_denominator_includes_unknown_cards():
    """AC6: the share's denominator is the total cards filed, including the
    cards the facts cannot tell who filed (unknown) — the service does not
    guess an unknown card's bucket and does not divide by the tellable cards.
    2024-01's filing facts show 10 cards filed: 4 by the crew, 2 unknown,
    2 by the Sponsor, 2 by the operator — the share reads 40, not 50 (4 of the
    8 tellable cards)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        for i in range(4):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tunk_{i}", "2024-01", "crew", "found")
            )
            assert status == 200
        # Two cards the facts cannot tell who filed: no filing-fact fields.
        for i in range(2):
            status, _ = _post_events(f"{base_url}/events", _filed_event(f"tunk_u{i}", "2024-01"))
            assert status == 200
        for i in range(2):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tunk_sp{i}", "2024-01", "sponsor")
            )
            assert status == 200
        for i in range(2):
            status, _ = _post_events(
                f"{base_url}/events", _filed_event(f"tunk_op{i}", "2024-01", "operator")
            )
            assert status == 200

        status, body = _get_json(
            f"{base_url}/trend?metric=self_filed_share_percent&start=2024-01&end=2024-01"
        )
        assert status == 200
        # 4 of 10 filed cards: the unknown cards count in the denominator.
        assert body["values"] == [{"sprint": "2024-01", "value": 40}]
    finally:
        conn.close()


@requires_db
def test_trend_unknown_metric_still_400_and_existing_measures_unchanged():
    """AC7: after the self-filed share measure is accepted, a metric name the
    service does not accept still answers 400 with the 'unknown metric' error
    naming it, and an existing measure over a window that also carries filing
    facts answers exactly the values it answers today — accepting the new
    measure changes no existing answer."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    base_url = f"http://127.0.0.1:{port}"
    try:
        # 2024-01: two cards started and finished; 2024-02: one.
        for card_id in ("tcompat_a", "tcompat_b"):
            status, _ = _post_events(
                f"{base_url}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-02T08:00:00Z",
                    sprint="2024-01",
                    created="2024-01-01",
                ),
            )
            assert status == 200
            status, _ = _post_events(
                f"{base_url}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-06T08:00:00Z",
                    sprint="2024-01",
                    created="2024-01-01",
                ),
            )
            assert status == 200
        status, _ = _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="tcompat_c",
                event_type="started",
                timestamp="2024-02-02T08:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        assert status == 200
        status, _ = _post_events(
            f"{base_url}/events",
            _make_event(
                card_id="tcompat_c",
                event_type="finished",
                timestamp="2024-02-06T08:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        assert status == 200
        # Filing facts in both sprints, so the window carries them.
        status, _ = _post_events(
            f"{base_url}/events", _filed_event("tcompat_f1", "2024-01", "crew", "found")
        )
        assert status == 200
        status, _ = _post_events(
            f"{base_url}/events", _filed_event("tcompat_f2", "2024-02", "sponsor")
        )
        assert status == 200

        # The unaccepted name still answers 400, naming the metric.
        status, body = _get_json(
            f"{base_url}/trend?metric=self_filed_share_pct&start=2024-01&end=2024-02"
        )
        assert status == 400
        assert "unknown metric" in body["error"]
        assert "self_filed_share_pct" in body["error"]

        # The existing measure answers exactly the values it answers today.
        status, body = _get_json(f"{base_url}/trend?metric=throughput&start=2024-01&end=2024-02")
        assert status == 200
        assert body["metric"] == "throughput"
        assert body["values"] == [
            {"sprint": "2024-01", "value": 2},
            {"sprint": "2024-02", "value": 1},
        ]
    finally:
        conn.close()


@requires_db
def test_range_filed_only_sprint_reads_null_for_delivery_measures():
    """AC1: A sprint whose only stored rows are 'filed' reads null for every
    delivery measure and appears in the window's no_data."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="fonly1", sprint="2026-01", filer="crew", opener="found"),
        )
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-01&end=2026-01")
        assert status == 200
        entry = body["sprints"]["2026-01"]
        assert entry["rework"] is None
        assert entry["cost"] is None
        assert entry["dora"] is None
        assert entry["working_time"] is None
        assert entry["cost_by_kind"] is None
        assert entry["model_time_split"] is None
        assert entry["idle"] is None
        assert entry["roster"] is None
        assert "2026-01" in body["window"]["no_data"]
    finally:
        conn.close()


@requires_db
def test_range_filed_only_sprint_still_answers_filed_split():
    """AC2: The same sprint (only filed rows) still answers its filed split."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="fonly1", sprint="2026-01", filer="crew", opener="found"),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="fonly2", sprint="2026-01", filer="sponsor"),
        )
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-01&end=2026-01")
        assert status == 200
        filed = body["sprints"]["2026-01"]["filed"]
        assert filed is not None
        assert filed["crew_total"] == 1
        assert filed["found"] == 1
        assert filed["from_process"] == 0
        assert filed["split"] == 0
        assert filed["unknown"] == 0
        assert filed["sponsor"] == 1
        assert filed["operator"] == 0
        assert filed["other"] == 0
        assert filed["total_cards"] == 2
        assert filed["self_filed_share"]["percent"] == 50
    finally:
        conn.close()


@requires_db
def test_range_filed_plus_delivery_sprint_unchanged():
    """AC3: A sprint with filed rows and delivery events answers exactly as it
    does without the filed rows: non-null delivery measures, not in no_data,
    filed field non-null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="fd1", sprint="2026-03", filer="crew", opener="found"),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="fd1",
                event_type="started",
                timestamp="2026-03-03T10:00:00Z",
                sprint="2026-03",
                created="2026-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="fd1",
                event_type="finished",
                timestamp="2026-03-07T10:00:00Z",
                sprint="2026-03",
                created="2026-03-01",
            ),
        )
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-03&end=2026-03")
        assert status == 200
        entry = body["sprints"]["2026-03"]
        assert entry["rework"] is not None
        assert entry["dora"] is not None
        assert "2026-03" not in body["window"]["no_data"]
        assert entry["filed"] is not None
        assert entry["filed"]["crew_total"] == 1
    finally:
        conn.close()


@requires_db
def test_trend_delivery_measures_null_for_filed_only_sprint():
    """AC4: /trend delivery measures read null for a filed-only sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="ft1", sprint="2026-05", filer="crew", opener="found"),
        )
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2026-05&end=2026-05"
        )
        assert status == 200
        values = {v["sprint"]: v["value"] for v in body["values"]}
        assert values["2026-05"] is None
    finally:
        conn.close()


@requires_db
def test_trend_self_filed_share_percent_filed_only_sprint():
    """AC5: /trend self_filed_share_percent keeps its value for a filed-only
    sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="fs1", sprint="2026-07", filer="crew", opener="found"),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _filed_event(card_id="fs2", sprint="2026-07", filer="sponsor"),
        )
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend"
            "?metric=self_filed_share_percent&start=2026-07&end=2026-08"
        )
        assert status == 200
        values = {v["sprint"]: v["value"] for v in body["values"]}
        assert values["2026-07"] == 50
        assert values["2026-08"] is None
    finally:
        conn.close()
