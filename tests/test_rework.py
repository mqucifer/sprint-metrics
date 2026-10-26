"""Tests for the rework answer: a sprint's send-backs to refinement, out of its started stories."""

from sprint_metrics.rework import calculate_rework


def test_rework_names_each_sent_back_story_with_step_and_reason():
    """AC1: two send-backs from different steps and for different reasons name each
    story by identifier with its step and reason, out of the stories started."""
    answer = calculate_rework(
        5,
        [
            ("s3", "Review", "contract_ruling"),
            ("s4", "QA", "blocked_session"),
        ],
    )
    assert answer["started"] == 5
    assert answer["sent_backs"] == [
        {"card_id": "s3", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]},
        {"card_id": "s4", "send_backs": [{"step": "QA", "reason": "blocked_session"}]},
    ]


def test_rework_step_is_the_role_sent_on_the_event_unmodified():
    """AC2: the step is the failure_role the crew sent on the returned event,
    unmodified — not a label the service invents."""
    for sent in ("Refinement", "review", "Team Lead", "Sprint 18's QA"):
        answer = calculate_rework(1, [("c1", sent, "reason")])
        assert answer["sent_backs"][0]["send_backs"][0]["step"] == sent


def test_rework_missing_step_or_reason_reads_as_null():
    """A send-back whose event carried no step, no reason, or neither, names
    the story with the missing field null, not a made-up label."""
    answer = calculate_rework(
        3,
        [
            ("c1", None, "reason"),
            ("c2", "step", None),
            ("c3", None, None),
        ],
    )
    assert answer["sent_backs"][0]["send_backs"][0] == {"step": None, "reason": "reason"}
    assert answer["sent_backs"][1]["send_backs"][0] == {"step": "step", "reason": None}
    assert answer["sent_backs"][2]["send_backs"][0] == {"step": None, "reason": None}


def test_rework_story_sent_back_twice_is_named_once_with_both_send_backs():
    """AC4: a story sent back twice in the sprint is named once, its send-backs
    each carrying their step and reason, and it counts once in the figure."""
    answer = calculate_rework(
        4,
        [
            ("c1", "Review", "contract_ruling"),
            ("c2", "QA", "blocked_session"),
            ("c1", "Refinement", "story_problem"),
        ],
    )
    assert len(answer["sent_backs"]) == 2
    c1 = next(entry for entry in answer["sent_backs"] if entry["card_id"] == "c1")
    assert c1["send_backs"] == [
        {"step": "Review", "reason": "contract_ruling"},
        {"step": "Refinement", "reason": "story_problem"},
    ]
    assert answer["started"] == 4


def test_rework_no_started_still_lists_the_send_back():
    """AC5: a sprint in which no story started still lists the send-back and
    reads 0 started — the answer neither invents a proportion nor drops it."""
    answer = calculate_rework(0, [("c1", "Review", "contract_ruling")])
    assert answer["started"] == 0
    assert answer["sent_backs"] == [
        {"card_id": "c1", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]}
    ]


def test_rework_no_returned_events_reads_as_no_data():
    """AC6: a sprint with events but no stored 'returned' events names no
    sent-back story (null, not an empty list) and does not assert a zero
    send-back count."""
    answer = calculate_rework(3, [])
    assert answer["started"] == 3
    assert answer["sent_backs"] is None
