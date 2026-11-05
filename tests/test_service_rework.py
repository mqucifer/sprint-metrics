"""Service tests for the returned event and the rework answer, and the sent_backs_count measure."""

from __future__ import annotations

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


def _returned_event(card_id, sprint, timestamp, failure_class=None, failure_role=None):
    """A 'returned' event: the story handed back to the Business Analyst.

    failure_class (the reason) and failure_role (the step that sent it back) are
    optional top-level fields, as the crew sends them.
    """
    event = {
        "api_version": "1",
        "card_id": card_id,
        "type": "returned",
        "timestamp": timestamp,
        "sprint": sprint,
        "card": {"created": "2024-01-01"},
    }
    if failure_class is not None:
        event["failure_class"] = failure_class
    if failure_role is not None:
        event["failure_role"] = failure_role
    return event


@requires_db
def test_range_rework_names_each_sent_back_story_out_of_started():
    """AC1: a sprint in which 5 stories started and 2 were sent back (different
    steps and reasons) carries a rework answer naming each sent-back story by
    identifier, its step and its reason, out of the 5 started."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e1_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        for i in range(1, 6):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_e2e1_s{i}",
                    event_type="started",
                    timestamp=f"2024-03-0{i}T10:00:00Z",
                    sprint="2024-03",
                    created="2024-03-01",
                ),
            )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e1_s3",
                "2024-03",
                "2024-03-12T10:00:00Z",
                failure_class="contract_ruling",
                failure_role="Review",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e1_s4",
                "2024-03",
                "2024-03-13T10:00:00Z",
                failure_class="blocked_session",
                failure_role="QA",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        rework = body["sprints"]["2024-03"]["rework"]
        assert rework["started"] == 5
        assert rework["sent_backs"] == [
            {"card_id": "rw_e2e1_s3", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]},
            {"card_id": "rw_e2e1_s4", "send_backs": [{"step": "QA", "reason": "blocked_session"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_step_is_unmodified_role_sent_on_event():
    """AC2: the rework step is the failure_role the crew sent on the returned
    event, unmodified — not a label the service invents."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e2_a",
                event_type="started",
                timestamp="2024-03-01T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e2_a",
                "2024-03",
                "2024-03-05T10:00:00Z",
                failure_class="reason",
                failure_role="Sprint 3's Team Lead",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        rework = body["sprints"]["2024-03"]["rework"]
        assert rework["sent_backs"][0]["send_backs"][0]["step"] == "Sprint 3's Team Lead"
    finally:
        conn.close()


@requires_db
def test_range_rework_counts_in_the_sprint_of_the_returned_event():
    """AC3: a story that started in sprint A and was sent back in sprint B is
    named in B's rework against B's started stories, and A's rework does not
    carry it."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e3_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-04', '2024-05')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Five stories start in 2024-04; one of them (rw_e2e3_m) is sent back in 2024-05.
        for i in range(1, 6):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_e2e3_s{i}",
                    event_type="started",
                    timestamp=f"2024-04-0{i}T10:00:00Z",
                    sprint="2024-04",
                    created="2024-04-01",
                ),
            )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e3_m",
                event_type="started",
                timestamp="2024-04-15T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e3_m",
                "2024-05",
                "2024-05-03T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-04&end=2024-05")
        assert status == 200
        sprints = body["sprints"]
        # A's rework names no sent-back story (it has events but no returned rows).
        assert sprints["2024-04"]["rework"]["started"] == 6
        assert sprints["2024-04"]["rework"]["sent_backs"] is None
        # B's rework names the send-back against B's started stories (0 started in B).
        assert sprints["2024-05"]["rework"]["started"] == 0
        assert sprints["2024-05"]["rework"]["sent_backs"] == [
            {
                "card_id": "rw_e2e3_m",
                "send_backs": [{"step": "Refinement", "reason": "story_problem"}],
            }
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_story_sent_back_twice_is_named_once():
    """AC4: a story sent back twice in the same sprint is named once, with both
    send-backs each carrying their step and reason, and it counts once in the
    out-of-started figure."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e4_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-06'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        for i in range(1, 5):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_e2e4_s{i}",
                    event_type="started",
                    timestamp=f"2024-06-0{i}T10:00:00Z",
                    sprint="2024-06",
                    created="2024-06-01",
                ),
            )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e4_s1",
                "2024-06",
                "2024-06-10T10:00:00Z",
                failure_class="contract_ruling",
                failure_role="Review",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e4_s1",
                "2024-06",
                "2024-06-12T10:00:00Z",
                failure_class="blocked_session",
                failure_role="QA",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        rework = body["sprints"]["2024-06"]["rework"]
        assert rework["started"] == 4
        # The story is named once even though it was sent back twice.
        assert [entry["card_id"] for entry in rework["sent_backs"]] == ["rw_e2e4_s1"]
        assert rework["sent_backs"][0]["send_backs"] == [
            {"step": "Review", "reason": "contract_ruling"},
            {"step": "QA", "reason": "blocked_session"},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_lists_send_back_with_zero_started():
    """AC5: a sprint in which no story started but a story was sent back still
    lists the send-back and reads 0 started — it neither invents a proportion
    nor drops the send-back."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e5_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-07'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e5_x",
                "2024-07",
                "2024-07-03T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-07&end=2024-07")
        assert status == 200
        rework = body["sprints"]["2024-07"]["rework"]
        assert rework["started"] == 0
        assert rework["sent_backs"] == [
            {"card_id": "rw_e2e5_x", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]}
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_null_for_empty_sprint_and_no_data_without_returned():
    """AC6: a sprint with no events at all reads rework null (no data, not
    zero-filled); a sprint with events but no stored 'returned' events names no
    sent-back story and does not assert a zero send-back count."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e6_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-08', '2024-09')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-08 has events (one started+finished story); 2024-09 has none.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e6_a",
                event_type="started",
                timestamp="2024-08-03T10:00:00Z",
                sprint="2024-08",
                created="2024-08-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e6_a",
                event_type="finished",
                timestamp="2024-08-07T10:00:00Z",
                sprint="2024-08",
                created="2024-08-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-08&end=2024-09")
        assert status == 200
        sprints = body["sprints"]
        # The empty sprint reads no data, not a zero-filled answer.
        assert sprints["2024-09"]["rework"] is None
        assert sprints["2024-09"]["throughput"] is None
        # The events-but-no-returned sprint names no sent-back story (null, not
        # an empty list) and carries its started count.
        assert sprints["2024-08"]["rework"] == {"started": 1, "sent_backs": None}
    finally:
        conn.close()


@requires_db
def test_range_rework_changes_no_other_metric():
    """AC7: a sent-back story that is never re-completed changes none of the
    other metrics; the already-shipping keys keep their values and shape."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e7_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # A story that starts and finishes (throughput 1, first attempt 100%).
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e7_done",
                event_type="started",
                timestamp="2024-10-03T10:00:00Z",
                sprint="2024-10",
                created="2024-10-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e7_done",
                event_type="finished",
                timestamp="2024-10-07T10:00:00Z",
                sprint="2024-10",
                created="2024-10-01",
            ),
        )
        status, before = _get_json(f"http://127.0.0.1:{port}/range?start=2024-10&end=2024-10")
        assert status == 200
        # A second story starts and is sent back to refinement, never re-completed.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e7_back",
                event_type="started",
                timestamp="2024-10-04T10:00:00Z",
                sprint="2024-10",
                created="2024-10-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e7_back",
                "2024-10",
                "2024-10-06T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )
        status, after = _get_json(f"http://127.0.0.1:{port}/range?start=2024-10&end=2024-10")
        assert status == 200
        before_entry = {
            k: v for k, v in before["sprints"]["2024-10"].items()
            if k not in ("rework", "working_time", "session_stories")
        }
        after_entry = {
            k: v for k, v in after["sprints"]["2024-10"].items()
            if k not in ("rework", "working_time", "session_stories")
        }
        assert before_entry == after_entry
        # The send-back completes no story and adds no review/QA return.
        assert after_entry["throughput"] == 1
        assert after_entry["failure_breakdown"] == []
        assert after_entry["top_failure_causes"] == []
        assert after["sprints"]["2024-10"]["rework"]["sent_backs"] == [
            {"card_id": "rw_e2e7_back", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]}
        ]
        # session_stories gains a null entry for the new card while retaining
        # existing values for other stories.
        after_ss = after["sprints"]["2024-10"]["session_stories"]
        assert after_ss["rw_e2e7_back"] is None
        assert after_ss["rw_e2e7_done"] is None
    finally:
        conn.close()


@requires_db
def test_range_rework_qa_returns_named_separately_from_sent_backs():
    """AC1: a sprint in which one story was sent back to refinement and another
    was bounced at review (an attempt_failed on a completed card) carries a
    rework answer with two labeled parts, each naming its stories."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa1_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Story 1: sent back to refinement (returned event)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa1_s1",
                event_type="started",
                timestamp="2024-11-02T10:00:00Z",
                sprint="2024-11",
                created="2024-11-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_qa1_s1",
                "2024-11",
                "2024-11-05T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )
        # Story 2: bounced at review/QA (attempt_failed on a completed card)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa1_s2",
                event_type="started",
                timestamp="2024-11-03T10:00:00Z",
                sprint="2024-11",
                created="2024-11-01",
            ),
        )
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa1_s2",
            "type": "attempt_failed",
            "timestamp": "2024-11-06T10:00:00Z",
            "sprint": "2024-11",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2024-11-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa1_s2",
                event_type="finished",
                timestamp="2024-11-07T10:00:00Z",
                sprint="2024-11",
                created="2024-11-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-11&end=2024-11")
        assert status == 200
        rework = body["sprints"]["2024-11"]["rework"]
        assert rework["started"] == 2
        assert rework["sent_backs"] == [
            {"card_id": "rw_qa1_s1", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]},
        ]
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa1_s2", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_by_step_groups_each_part():
    """AC3: the rework answer's by_step shows the count of rework per step
    for each part, so the reader sees which step the sprint's rework
    concentrates in."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-12'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Two send-backs from different steps
        for i, (role, cls) in enumerate([("Review", "contract_ruling"), ("QA", "blocked_session")], start=1):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_qa2_s{i}",
                    event_type="started",
                    timestamp=f"2024-12-0{i}T10:00:00Z",
                    sprint="2024-12",
                    created="2024-12-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _returned_event(
                    f"rw_qa2_s{i}",
                    "2024-12",
                    f"2024-12-0{i}T12:00:00Z",
                    failure_class=cls,
                    failure_role=role,
                ),
            )
        # Two review/QA returns from the same step
        for i in (3, 4):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_qa2_s{i}",
                    event_type="started",
                    timestamp=f"2024-12-0{i}T10:00:00Z",
                    sprint="2024-12",
                    created="2024-12-01",
                ),
            )
            attempt_failed = {
                "api_version": "1",
                "card_id": f"rw_qa2_s{i}",
                "type": "attempt_failed",
                "timestamp": f"2024-12-0{i}T12:00:00Z",
                "sprint": "2024-12",
                "attempt_number": 1,
                "failure_class": "parse_error",
                "failure_role": "QA",
                "card": {"created": "2024-12-01"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_qa2_s{i}",
                    event_type="finished",
                    timestamp=f"2024-12-0{i}T14:00:00Z",
                    sprint="2024-12",
                    created="2024-12-01",
                ),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-12&end=2024-12")
        assert status == 200
        rework = body["sprints"]["2024-12"]["rework"]
        assert rework["by_step"] == {
            "sent_backs": {"Review": 1, "QA": 1},
            "qa_returns": {"QA": 2},
        }
    finally:
        conn.close()


@requires_db
def test_range_rework_qa_returns_only_no_sent_backs():
    """AC5: a sprint with review/QA returns but no send-backs carries
    sent_backs null and lists its qa_returns — the two parts do not
    borrow each other's data."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa3_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa3_s1",
                event_type="started",
                timestamp="2025-01-02T10:00:00Z",
                sprint="2025-01",
                created="2025-01-01",
            ),
        )
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa3_s1",
            "type": "attempt_failed",
            "timestamp": "2025-01-03T10:00:00Z",
            "sprint": "2025-01",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2025-01-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa3_s1",
                event_type="finished",
                timestamp="2025-01-04T10:00:00Z",
                sprint="2025-01",
                created="2025-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2025-01&end=2025-01")
        assert status == 200
        rework = body["sprints"]["2025-01"]["rework"]
        assert rework["started"] == 1
        assert rework["sent_backs"] is None
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa3_s1", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
        assert rework["by_step"] == {"qa_returns": {"Review": 1}}
    finally:
        conn.close()


@requires_db
def test_range_rework_story_in_both_parts_separately():
    """AC2: a story that both went back to the BA (returned event) and
    bounced at review/QA (attempt_failed on a completed card) appears in
    both parts, separately."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa4_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-02'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa4_s1",
                event_type="started",
                timestamp="2025-02-02T10:00:00Z",
                sprint="2025-02",
                created="2025-02-01",
            ),
        )
        # Bounced at review
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa4_s1",
            "type": "attempt_failed",
            "timestamp": "2025-02-03T10:00:00Z",
            "sprint": "2025-02",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2025-02-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        # Sent back to refinement
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_qa4_s1",
                "2025-02",
                "2025-02-04T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )
        # Completed
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa4_s1",
                event_type="finished",
                timestamp="2025-02-05T10:00:00Z",
                sprint="2025-02",
                created="2025-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2025-02&end=2025-02")
        assert status == 200
        rework = body["sprints"]["2025-02"]["rework"]
        # The story appears in both parts, separately
        assert rework["sent_backs"] == [
            {"card_id": "rw_qa4_s1", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]},
        ]
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa4_s1", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_failure_breakdown_unchanged():
    """AC4: the rework answer's qa_returns uses the same (failure class,
    returning role) values as failure_breakdown, and failure_breakdown
    keeps its values and shape."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa5_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa5_s1",
                event_type="started",
                timestamp="2025-03-02T10:00:00Z",
                sprint="2025-03",
                created="2025-03-01",
            ),
        )
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa5_s1",
            "type": "attempt_failed",
            "timestamp": "2025-03-03T10:00:00Z",
            "sprint": "2025-03",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2025-03-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa5_s1",
                event_type="finished",
                timestamp="2025-03-04T10:00:00Z",
                sprint="2025-03",
                created="2025-03-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2025-03&end=2025-03")
        assert status == 200
        entry = body["sprints"]["2025-03"]
        # failure_breakdown keeps its shape and values
        assert entry["failure_breakdown"] == [
            {"class": "contract_ruling", "role": "Review", "count": 1},
        ]
        assert entry["top_failure_causes"] == [
            {"class": "contract_ruling", "role": "Review", "count": 1},
        ]
        # qa_returns uses the same (class, role) values
        rework = entry["rework"]
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa5_s1", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_post_returned_stores_failure_class_role_and_epic():
    """AC1: POST /events with type='returned' carrying failure_class, failure_role,
    and epic answers 200 and the stored returned row carries all three values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'r1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "r1",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "failure_class": "blocked_session",
            "failure_role": "review",
            "epic": "epic-7",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT failure_class, failure_role, epic FROM sprint_metrics.board_events "
            "WHERE card_id = 'r1' AND type = 'returned'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "blocked_session"
        assert rows[0][1] == "review"
        assert rows[0][2] == "epic-7"
    finally:
        conn.close()


@requires_db
def test_post_returned_without_optional_fields_stores_null():
    """AC2: POST /events with type='returned' and no failure_class, failure_role, or
    epic answers 200 and stores those columns as NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'r2'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "r2",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT failure_class, failure_role, epic FROM sprint_metrics.board_events "
            "WHERE card_id = 'r2' AND type = 'returned'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
        assert rows[0][1] is None
        assert rows[0][2] is None
    finally:
        conn.close()


@requires_db
def test_post_returned_resend_fills_null_keeps_existing():
    """AC3: re-sending a stored 'returned' event with a failure_class the first send
    left NULL answers 200; the NULL field takes the supplied value and fields that
    already hold a value are not changed."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'r3'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        first = {
            "api_version": "1",
            "card_id": "r3",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "failure_role": "review",
            "epic": "epic-7",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", first)
        assert status == 200
        assert "error" not in body

        resend = {
            "api_version": "1",
            "card_id": "r3",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "failure_class": "blocked_session",
            "failure_role": "qa",
            "epic": "epic-9",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", resend)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT failure_class, failure_role, epic FROM sprint_metrics.board_events "
            "WHERE card_id = 'r3' AND type = 'returned'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "blocked_session"
        assert rows[0][1] == "review"
        assert rows[0][2] == "epic-7"
    finally:
        conn.close()


@requires_db
def test_trend_sent_backs_count_two_sprints():
    """AC1: GET /trend?metric=sent_backs_count returns 200 with the count of
    distinct stories sent back per sprint; a story sent back twice counts once."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('sb_trend_a', 'sb_trend_b', 'sb_trend_c', 'sb_trend_d')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one started event and two returned events on the same story
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_a",
                event_type="returned",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_a",
                event_type="returned",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: two distinct stories sent back
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_b",
                event_type="returned",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_c",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_c",
                event_type="returned",
                timestamp="2024-02-04T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=sent_backs_count&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["api_version"] == API_VERSION
        assert body["metric"] == "sent_backs_count"
        assert body["start"] == "2024-01"
        assert body["end"] == "2024-02"
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 1}
        assert body["values"][1] == {"sprint": "2024-02", "value": 2}
    finally:
        conn.close()


@requires_db
def test_trend_sent_backs_count_null_when_no_returned_events():
    """AC2: a sprint with events but no stored 'returned' events reads null,
    not zero — the service does not claim zero send-backs from an absence."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('sb_trend_e', 'sb_trend_f')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: a sprint with events but no returned events
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_e",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_e",
                event_type="finished",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: one story sent back
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_f",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_f",
                event_type="returned",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=sent_backs_count&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": 1}
    finally:
        conn.close()


@requires_db
def test_trend_sent_backs_count_response_shape():
    """AC3: the response carries api_version, metric, start, end, and a values
    array of sprint-and-value pairs with the value a whole number or null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('sb_trend_g')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_g",
                event_type="started",
                timestamp="2024-03-02T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="sb_trend_g",
                event_type="returned",
                timestamp="2024-03-03T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=sent_backs_count&start=2024-03&end=2024-04"
        )
        assert status == 200
        assert "api_version" in body
        assert "metric" in body
        assert "start" in body
        assert "end" in body
        assert "values" in body
        assert isinstance(body["values"], list)
        for entry in body["values"]:
            assert "sprint" in entry
            assert "value" in entry
            assert entry["value"] is None or isinstance(entry["value"], int)
    finally:
        conn.close()


@requires_db
def test_trend_sent_backs_count_empty_db_returns_nulls():
    """AC1/AC2: on an empty DB, all sprints read null (no events means no data)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=sent_backs_count&start=2024-01&end=2024-03"
        )
        assert status == 200
        assert len(body["values"]) == 3
        for entry in body["values"]:
            assert entry["value"] is None
    finally:
        conn.close()
