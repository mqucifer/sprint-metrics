"""Tests for the rework answer: a sprint's send-backs to refinement and its review/QA returns, each labeled and grouped by step."""

from datetime import date

from sprint_metrics.card import Card
from sprint_metrics.rework import calculate_rework, extract_qa_returns


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


# --- Review/QA returns part ---


def test_extract_qa_returns_names_completed_cards_with_failures():
    """AC2: extract_qa_returns returns (card_id, step, reason) for each
    return on a completed card, using the same (failure class, returning
    role) values as failure_breakdown."""
    card = Card(
        created=date(2024, 1, 1),
        started=date(2024, 1, 2),
        completed=date(2024, 1, 10),
        card_id="s1",
        failures=[("contract_ruling", "Review"), ("blocked_session", "QA")],
    )
    result = extract_qa_returns([card])
    assert result == [
        ("s1", "Review", "contract_ruling"),
        ("s1", "QA", "blocked_session"),
    ]


def test_extract_qa_returns_legacy_attempts():
    """AC2: a completed card with attempts > 1 and no failures list
    contributes one return using its failure_class and failure_role."""
    card = Card(
        created=date(2024, 1, 1),
        started=date(2024, 1, 2),
        completed=date(2024, 1, 10),
        attempts=3,
        failure_class="contract_ruling",
        failure_role="Review",
        card_id="s2",
    )
    result = extract_qa_returns([card])
    assert result == [("s2", "Review", "contract_ruling")]


def test_extract_qa_returns_skips_incomplete_cards():
    """AC2: a card that is not completed does not contribute a return."""
    card = Card(
        created=date(2024, 1, 1),
        started=date(2024, 1, 2),
        card_id="s3",
        failures=[("reason", "Review")],
    )
    result = extract_qa_returns([card])
    assert result == []


def test_rework_qa_returns_named_separately_from_sent_backs():
    """AC1: a story that both went back to the BA and bounced at review
    appears in both parts, separately — the reader cannot conflate them."""
    answer = calculate_rework(
        5,
        [("s1", "Review", "contract_ruling")],
        [("s1", "QA", "blocked_session"), ("s2", "Review", "story_problem")],
    )
    assert answer["sent_backs"] == [
        {"card_id": "s1", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]},
    ]
    assert answer["qa_returns"] == [
        {"card_id": "s1", "returns": [{"step": "QA", "reason": "blocked_session"}]},
        {"card_id": "s2", "returns": [{"step": "Review", "reason": "story_problem"}]},
    ]


def test_rework_by_step_groups_each_part_by_step():
    """AC3: by_step shows the count of rework per step for each part."""
    answer = calculate_rework(
        5,
        [("s1", "Review", "contract_ruling"), ("s2", "QA", "blocked_session")],
        [("s1", "QA", "blocked_session"), ("s3", "Review", "story_problem"), ("s3", "Review", "another")],
    )
    assert answer["by_step"] == {
        "sent_backs": {"Review": 1, "QA": 1},
        "qa_returns": {"QA": 1, "Review": 2},
    }


def test_rework_qa_returns_empty_reads_as_no_data():
    """AC5: a sprint with send-backs but no review/QA returns carries
    no qa_returns key — the two parts do not borrow each other's data."""
    answer = calculate_rework(
        3,
        [("s1", "Review", "contract_ruling")],
        [],
    )
    assert answer["sent_backs"] == [
        {"card_id": "s1", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]},
    ]
    assert "qa_returns" not in answer
    assert "by_step" not in answer


def test_rework_sent_backs_empty_qa_returns_present():
    """AC5: a sprint with review/QA returns but no send-backs carries
    sent_backs null and lists its qa_returns — the two parts do not
    borrow each other's data."""
    answer = calculate_rework(
        3,
        [],
        [("s1", "QA", "blocked_session")],
    )
    assert answer["sent_backs"] is None
    assert answer["qa_returns"] == [
        {"card_id": "s1", "returns": [{"step": "QA", "reason": "blocked_session"}]},
    ]
    assert answer["by_step"] == {"qa_returns": {"QA": 1}}


def test_rework_both_parts_empty_no_by_step():
    """AC3: when both parts are empty, by_step and qa_returns are absent."""
    answer = calculate_rework(3, [], [])
    assert answer["sent_backs"] is None
    assert "qa_returns" not in answer
    assert "by_step" not in answer


def test_rework_qa_returns_story_bounced_twice_named_once():
    """AC2: a story bounced at review/QA twice in the sprint is named once,
    its returns each carrying their step and reason."""
    answer = calculate_rework(
        4,
        [],
        [
            ("c1", "Review", "contract_ruling"),
            ("c1", "QA", "blocked_session"),
        ],
    )
    assert answer["qa_returns"] == [
        {
            "card_id": "c1",
            "returns": [
                {"step": "Review", "reason": "contract_ruling"},
                {"step": "QA", "reason": "blocked_session"},
            ],
        }
    ]
    assert answer["by_step"] == {"qa_returns": {"Review": 1, "QA": 1}}


def test_rework_without_qa_returns_keeps_old_shape():
    """When qa_returns is not provided (None), the answer has only
    started and sent_backs — the old shape."""
    answer = calculate_rework(3, [("s1", "Review", "reason")])
    assert set(answer.keys()) == {"started", "sent_backs"}


# --- Range attachment and description fragment ---


def test_attach_range_rework_lives_in_rework_module():
    """AC1: the rework attachment is importable from sprint_metrics.rework,
    not from sprint_metrics.service, where _attach_range_rework lived before
    the move — the definition lives in the rework module."""
    from sprint_metrics.rework import _attach_range_rework

    assert callable(_attach_range_rework)
    assert _attach_range_rework.__module__ == "sprint_metrics.rework"


def test_attach_range_rework_applies_each_entry_rework_object():
    """AC1: applying the rework attachment from rework.py puts each entry's
    rework object on its range entry: the sprint's started count, its labeled
    sent_backs, and its qa_returns and by_step where present, as it does
    today."""
    from sprint_metrics.rework import _attach_range_rework, calculate_rework

    rework = {
        "2024-08": calculate_rework(
            2,
            [("s1", "Review", "contract_ruling")],
            [("s2", "QA", "blocked_session")],
        ),
        "2024-09": calculate_rework(1, []),
    }
    labels = ["2024-08", "2024-09", "2024-10"]
    result = {"sprints": {label: {} for label in labels}}
    _attach_range_rework(result, labels, rework)

    assert result["sprints"]["2024-08"]["rework"] == {
        "started": 2,
        "sent_backs": [
            {"card_id": "s1", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]}
        ],
        "qa_returns": [
            {"card_id": "s2", "returns": [{"step": "QA", "reason": "blocked_session"}]}
        ],
        "by_step": {"sent_backs": {"Review": 1}, "qa_returns": {"QA": 1}},
    }
    assert result["sprints"]["2024-09"]["rework"] == {"started": 1, "sent_backs": None}
    # The no-events sprint has no rework object: rework null, not zero.
    assert result["sprints"]["2024-10"]["rework"] is None


def test_range_rework_description_fragment_lives_in_rework_module():
    """AC4: the rework answer's description fragment is owned by rework.py and
    tells the reader what the generated /range row tells them about rework:
    each entry carries two labeled parts — sent_backs (the stories sent back
    to the Business Analyst, its returned events, out of the stories started
    that sprint, each story named by its identifier, each send-back carrying
    the step it was sent back from and the reason) and qa_returns (the
    review/QA returns, each carrying the step it was returned from and the
    cause); a send-back counts in the sprint of the returned event; by_step
    groups each part's returns by step; sprints with no events return
    all-null values, rework included."""
    from sprint_metrics.rework import _RANGE_REWORK_DESCRIPTION
    from sprint_metrics.service import SERVICE_ENDPOINTS

    for phrase in (
        "two labeled parts",
        "sent_backs",
        "Business Analyst",
        "stories started",
        "identifier",
        "step it was sent back from",
        "reason",
        "qa_returns",
        "step it was returned from",
        "cause",
        "sprint of the returned event",
        "by_step groups",
        "all-null",
    ):
        assert phrase in _RANGE_REWORK_DESCRIPTION, f"fragment missing {phrase!r}"
    # The generated /range row tells the reader exactly this: the fragment is
    # composed into the /range endpoint description.
    range_desc = next(desc for method, path, desc in SERVICE_ENDPOINTS if path == "/range")
    assert _RANGE_REWORK_DESCRIPTION in range_desc
