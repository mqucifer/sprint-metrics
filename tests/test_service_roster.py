"""Service tests for the roster answer on /range."""

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
def test_range_roster_completed_stories_and_links():
    """AC1: a sprint with finished c1 (no epic) and finished c2, c3 (both with
    epic E1 and goal G1) yields roster with completed_stories [c1, c2, c3],
    released_epics [E1], achieved_goals [G1]."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ro_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # c1: no epic, no goal
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ro_c1",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ro_c1",
                event_type="finished",
                timestamp="2024-01-07T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # c2: epic E1, goal G1
        event_c2 = _make_event(
            card_id="ro_c2",
            event_type="finished",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        event_c2["epic"] = "E1"
        event_c2["goal"] = "G1"
        _post_events(f"http://127.0.0.1:{port}/events", event_c2)
        # c3: epic E1, goal G1
        event_c3 = _make_event(
            card_id="ro_c3",
            event_type="finished",
            timestamp="2024-01-06T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        event_c3["epic"] = "E1"
        event_c3["goal"] = "G1"
        _post_events(f"http://127.0.0.1:{port}/events", event_c3)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        roster = body["sprints"]["2024-01"]["roster"]
        assert roster["completed_stories"] == ["ro_c1", "ro_c2", "ro_c3"]
        assert roster["released_epics"] == ["E1"]
        assert roster["achieved_goals"] == ["G1"]
    finally:
        conn.close()


@requires_db
def test_range_roster_epic_releases_in_last_story_sprint():
    """AC2: epic E2 with c4 finishing in 2024-01 and c5 in 2024-02 → only
    2024-02's roster names E2 as released; 2024-01's does not."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ro_e2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # c4: epic E2, finishes in 2024-01
        event_c4 = _make_event(
            card_id="ro_e2_c4",
            event_type="finished",
            timestamp="2024-01-10T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        event_c4["epic"] = "E2"
        _post_events(f"http://127.0.0.1:{port}/events", event_c4)
        # c5: epic E2, finishes in 2024-02 (later)
        event_c5 = _make_event(
            card_id="ro_e2_c5",
            event_type="finished",
            timestamp="2024-02-10T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        event_c5["epic"] = "E2"
        _post_events(f"http://127.0.0.1:{port}/events", event_c5)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        # 2024-01: E2's last story is NOT here, so released_epics is empty
        assert sprints["2024-01"]["roster"]["released_epics"] == []
        # 2024-02: E2's last story IS here
        assert sprints["2024-02"]["roster"]["released_epics"] == ["E2"]
    finally:
        conn.close()


@requires_db
def test_range_roster_superseded_story_not_completed():
    """AC3: a story whose only terminal event is 'superseded' appears in no
    sprint's completed_stories and completes no epic."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ro_sup_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # ro_sup_c1: started + superseded (no finished)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ro_sup_c1",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        sup_event = {
            "api_version": "1",
            "card_id": "ro_sup_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
            "because": "sponsor",
            "epic": "E3",
        }
        _post_events(f"http://127.0.0.1:{port}/events", sup_event)
        # ro_sup_c2: finished, same epic E3
        event_c2 = _make_event(
            card_id="ro_sup_c2",
            event_type="finished",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        event_c2["epic"] = "E3"
        _post_events(f"http://127.0.0.1:{port}/events", event_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        roster = body["sprints"]["2024-01"]["roster"]
        # ro_sup_c1 is NOT in completed_stories (it was superseded, not finished)
        assert "ro_sup_c1" not in roster["completed_stories"]
        assert "ro_sup_c2" in roster["completed_stories"]
        # E3 releases via ro_sup_c2 (the only finished story)
        assert roster["released_epics"] == ["E3"]
    finally:
        conn.close()


@requires_db
def test_range_roster_goal_achieved_in_last_epic_sprint():
    """AC3: a Goal whose last epic's last story completes in a later sprint
    is named only in that sprint's achieved_goals."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ro_g2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Epic E4: story ro_g2_c1 finishes in 2024-01, goal G2
        event_c1 = _make_event(
            card_id="ro_g2_c1",
            event_type="finished",
            timestamp="2024-01-10T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        event_c1["epic"] = "E4"
        event_c1["goal"] = "G2"
        _post_events(f"http://127.0.0.1:{port}/events", event_c1)
        # Epic E5: story ro_g2_c2 finishes in 2024-02, goal G2 (later)
        event_c2 = _make_event(
            card_id="ro_g2_c2",
            event_type="finished",
            timestamp="2024-02-10T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        event_c2["epic"] = "E5"
        event_c2["goal"] = "G2"
        _post_events(f"http://127.0.0.1:{port}/events", event_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        # G2 is achieved in 2024-02 (where E5's last story finishes), not 2024-01
        assert "G2" not in sprints["2024-01"]["roster"]["achieved_goals"]
        assert sprints["2024-02"]["roster"]["achieved_goals"] == ["G2"]
    finally:
        conn.close()


@requires_db
def test_range_roster_null_epic_and_goal_parts():
    """AC4: a sprint whose stories carry no epic or goal link reads null for
    released_epics and achieved_goals, while completed_stories still names
    the sprint's completed stories; a sprint with no events reads roster null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ro_noepic_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one story with no epic/goal link
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ro_noepic_c1",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ro_noepic_c1",
                event_type="finished",
                timestamp="2024-01-07T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: no events at all

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        # 2024-01: has events, no links → null for epic/goal parts
        roster_01 = sprints["2024-01"]["roster"]
        assert roster_01["completed_stories"] == ["ro_noepic_c1"]
        assert roster_01["released_epics"] is None
        assert roster_01["achieved_goals"] is None
        # 2024-02: no events → roster is null
        assert sprints["2024-02"]["roster"] is None
    finally:
        conn.close()


@requires_db
def test_range_roster_mixed_sprints_per_sprint_null():
    """AC4: in a mixed range, a pre-Goal sprint (no links) reads null for
    epic/goal parts per-sprint (not empty list), while a linked sprint
    carries its lists."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ro_mix_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: story with no links
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ro_mix_c1",
                event_type="finished",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: story with epic E5 and goal G5
        event_c2 = _make_event(
            card_id="ro_mix_c2",
            event_type="finished",
            timestamp="2024-02-05T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        event_c2["epic"] = "E5"
        event_c2["goal"] = "G5"
        _post_events(f"http://127.0.0.1:{port}/events", event_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        # 2024-01: no links → null
        assert sprints["2024-01"]["roster"]["released_epics"] is None
        assert sprints["2024-01"]["roster"]["achieved_goals"] is None
        # 2024-02: has links → lists
        assert sprints["2024-02"]["roster"]["released_epics"] == ["E5"]
        assert sprints["2024-02"]["roster"]["achieved_goals"] == ["G5"]
    finally:
        conn.close()


def test_sprint_range_schema_declares_roster_on_sprint_entry():
    """AC7: SPRINT_RANGE_SCHEMA documents roster as an optional property per
    sprint entry (not in required), with completed_stories (array of strings),
    released_epics and achieved_goals (array-or-null of strings)."""
    from sprint_metrics.schema import SPRINT_RANGE_SCHEMA

    sprint_entry = SPRINT_RANGE_SCHEMA["properties"]["sprints"]["additionalProperties"]
    # roster is NOT in the required list
    assert "roster" not in sprint_entry["required"]
    # roster is in properties
    roster_schema = sprint_entry["properties"]["roster"]
    assert roster_schema["type"] == ["object", "null"]
    assert roster_schema["required"] == ["completed_stories", "released_epics", "achieved_goals"]
    assert roster_schema["properties"]["completed_stories"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert roster_schema["properties"]["released_epics"] == {
        "type": ["array", "null"],
        "items": {"type": "string"},
    }
    assert roster_schema["properties"]["achieved_goals"] == {
        "type": ["array", "null"],
        "items": {"type": "string"},
    }
