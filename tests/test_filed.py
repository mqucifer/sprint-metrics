"""Tests for the per-sprint filed-split answer: how much of the sprint's filed work the crew gave itself."""

from sprint_metrics.filed import calculate_filed_split


def _crew_found(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n crew-filed cards with opener 'found'."""
    return [(f"cf_{i}", "crew", "found", None) for i in range(n)]


def _crew_process(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n crew-filed cards with opener 'process'."""
    return [(f"cp_{i}", "crew", "process", None) for i in range(n)]


def _crew_split(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n crew-filed cards with opener 'split'."""
    return [(f"cs_{i}", "crew", "split", None) for i in range(n)]


def _crew_unknown(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n crew-filed cards with no opener (unidentifiable)."""
    return [(f"cu_{i}", "crew", None, None) for i in range(n)]


def _sponsor(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n sponsor-filed cards."""
    return [(f"sp_{i}", "sponsor", None, None) for i in range(n)]


def _operator(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n operator-filed cards."""
    return [(f"op_{i}", "operator", None, None) for i in range(n)]


def _other(n: int) -> list[tuple[str, str | None, str | None, str | None]]:
    """Build n cards filed by 'other'."""
    return [(f"ot_{i}", "other", None, None) for i in range(n)]


def test_worked_example_goal_37():
    """AC1: the Goal's worked example — 25 crew (10 found, 12 process, 3 split,
    0 unknown) plus 1 Sponsor and 1 operator, of 27 total cards."""
    events = (
        _crew_found(10)
        + _crew_process(12)
        + _crew_split(3)
        + _sponsor(1)
        + _operator(1)
    )
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 25
    assert answer["found"] == 10
    assert answer["from_process"] == 12
    assert answer["split"] == 3
    assert answer["unknown"] == 0
    assert answer["sponsor"] == 1
    assert answer["operator"] == 1
    assert answer["other"] == 0
    assert answer["total_cards"] == 27


def test_buckets_partition_the_sprint():
    """AC2: for any sprint's filing facts, crew total = found + from_process +
    split + unknown, and crew + sponsor + operator + other = total_cards."""
    events = (
        _crew_found(3)
        + _crew_process(5)
        + _crew_split(2)
        + _crew_unknown(1)
        + _sponsor(4)
        + _operator(2)
        + _other(1)
    )
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == answer["found"] + answer["from_process"] + answer["split"] + answer["unknown"]
    assert (
        answer["crew_total"]
        + answer["sponsor"]
        + answer["operator"]
        + answer["other"]
        == answer["total_cards"]
    )


def test_partition_holds_for_zero_crew():
    """AC2: the partition holds even when the crew filed nothing."""
    events = _sponsor(2) + _operator(1) + _other(3)
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 0
    assert answer["found"] == 0
    assert answer["from_process"] == 0
    assert answer["split"] == 0
    assert answer["unknown"] == 0
    assert answer["total_cards"] == 6


def test_crew_card_with_no_opener_counts_as_unknown():
    """AC3: a crew-filed card whose opener was not sent on the event counts in
    the unknown bucket and in the crew total; no bucket is inferred."""
    events = [
        ("c1", "crew", None, None),
    ]
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 1
    assert answer["unknown"] == 1
    assert answer["found"] == 0
    assert answer["from_process"] == 0
    assert answer["split"] == 0


def test_crew_card_with_unidentifiable_opener_counts_as_unknown():
    """AC3: a crew-filed card whose opener is a value that is not found,
    process, or split counts in the unknown bucket — never guessed."""
    events = [
        ("c1", "crew", "qa-suite test failed", "qa-suite"),
        ("c2", "crew", "something else entirely", None),
    ]
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 2
    assert answer["unknown"] == 2
    assert answer["found"] == 0
    assert answer["from_process"] == 0
    assert answer["split"] == 0


def test_crew_card_unknown_includes_in_crew_total():
    """AC3: the unknown bucket is included in the crew total — the card was
    filed by the crew, we just can't tell what opened it."""
    events = [
        ("c1", "crew", "found", None),
        ("c2", "crew", None, None),
        ("c3", "crew", "mystery", None),
    ]
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 3
    assert answer["found"] == 1
    assert answer["unknown"] == 2


def test_no_filing_facts_is_not_zero():
    """AC4: the caller distinguishes no filing facts (empty list) from filing
    facts with zero crew. An empty list is the signal for null (no data);
    a non-empty list with no crew cards is zero counts. This test verifies
    the function handles the zero-crew case correctly."""
    events = _sponsor(1) + _operator(1)
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 0
    assert answer["found"] == 0
    assert answer["from_process"] == 0
    assert answer["split"] == 0
    assert answer["unknown"] == 0
    assert answer["sponsor"] == 1
    assert answer["operator"] == 1
    assert answer["other"] == 0
    assert answer["total_cards"] == 2


def test_self_filed_share_worked_example():
    """AC5: the self-filed share is 25 of 27, carried with numerator and
    denominator."""
    events = (
        _crew_found(10)
        + _crew_process(12)
        + _crew_split(3)
        + _sponsor(1)
        + _operator(1)
    )
    answer = calculate_filed_split(events)
    assert answer["self_filed_share"]["numerator"] == 25
    assert answer["self_filed_share"]["denominator"] == 27
    assert answer["self_filed_share"]["percent"] == 93  # round(25/27*100) = 93


def test_self_filed_share_all_crew():
    """AC5: when the crew filed everything, the share is 100 percent."""
    events = _crew_found(5)
    answer = calculate_filed_split(events)
    assert answer["self_filed_share"]["percent"] == 100
    assert answer["self_filed_share"]["numerator"] == 5
    assert answer["self_filed_share"]["denominator"] == 5


def test_self_filed_share_zero_crew():
    """AC5: when the crew filed nothing, the share is 0 percent."""
    events = _sponsor(3) + _operator(2)
    answer = calculate_filed_split(events)
    assert answer["self_filed_share"]["percent"] == 0
    assert answer["self_filed_share"]["numerator"] == 0
    assert answer["self_filed_share"]["denominator"] == 5


def test_same_card_id_different_projects_counts_twice():
    """R21: a card '123' in two repos counts as two distinct cards — the
    project field keeps them distinct."""
    events = [
        ("123", "crew", "found", "repo-a"),
        ("123", "crew", "process", "repo-b"),
    ]
    answer = calculate_filed_split(events)
    assert answer["crew_total"] == 2
    assert answer["found"] == 1
    assert answer["from_process"] == 1
    assert answer["total_cards"] == 2
