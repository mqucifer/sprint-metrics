"""Tests for the Card dataclass and card parsing in sprint_metrics.card."""

from datetime import UTC, date, datetime

import pytest

from sprint_metrics.card import Card, _as_cards, _load_cards, _parse_date, parse_card


def test_card_properties():
    """AC1: Card imported from sprint_metrics.card has correct is_completed,
    cycle_time, and lead_time properties."""
    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3), completed=date(2024, 1, 7))
    assert card.is_completed is True
    assert card.cycle_time == 4
    assert card.lead_time == 6


def test_card_not_completed():
    """A card without a completed date is not completed and has zero cycle/lead time."""
    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3))
    assert card.is_completed is False
    assert card.cycle_time == 0
    assert card.lead_time == 0


def test_card_completed_without_start():
    """A card completed without being started has lead time but no cycle time."""
    card = Card(created=date(2024, 1, 1), completed=date(2024, 1, 7))
    assert card.is_completed is True
    assert card.cycle_time == 0
    assert card.lead_time == 6


def test_load_cards_invalid_date():
    """AC2: _load_cards raises ValueError containing the bad date string."""
    with pytest.raises(ValueError, match="not-a-date"):
        _load_cards('[{"created": "not-a-date"}]')


def test_load_cards_valid():
    """_load_cards parses a valid JSON list of cards."""
    cards = _load_cards(
        '[{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]'
    )
    assert len(cards) == 1
    assert cards[0].created == date(2024, 1, 1)
    assert cards[0].started == date(2024, 1, 3)
    assert cards[0].completed == date(2024, 1, 7)
    assert cards[0].is_completed is True


def test_load_cards_empty_string():
    """An empty string produces an empty list."""
    assert _load_cards("") == []


def test_load_cards_not_a_list():
    """A JSON object instead of a list raises TypeError."""
    with pytest.raises(TypeError, match="JSON list"):
        _load_cards('{"created": "2024-01-01"}')


def test_parse_card_missing_created():
    """A card without a created date raises ValueError."""
    with pytest.raises(ValueError, match="created"):
        parse_card({"started": "2024-01-03"})


def test_parse_card_valid():
    """parse_card builds a Card from a valid mapping."""
    card = parse_card({"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"})
    assert card.created == date(2024, 1, 1)
    assert card.started == date(2024, 1, 3)
    assert card.completed == date(2024, 1, 7)
    assert card.blocked_since is None


def test_parse_date_none():
    """_parse_date returns None for None input."""
    assert _parse_date(None, "created") is None


def test_parse_date_empty_string():
    """_parse_date returns None for empty string."""
    assert _parse_date("", "created") is None


def test_parse_date_invalid():
    """_parse_date raises ValueError for an invalid date string."""
    with pytest.raises(ValueError, match="not-a-date"):
        _parse_date("not-a-date", "created")


def test_parse_date_non_string():
    """_parse_date raises TypeError for a non-string, non-None value."""
    with pytest.raises(TypeError, match="created"):
        _parse_date(42, "created")


def test_as_cards_mixed():
    """_as_cards accepts both Card instances and raw mappings."""
    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3), completed=date(2024, 1, 7))
    raw = {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-05"}
    result = _as_cards([card, raw])
    assert len(result) == 2
    assert result[0] is card
    assert result[1].created == date(2024, 1, 1)
    assert result[1].completed == date(2024, 1, 5)


def test_parse_card_with_attempts_and_failure_fields():
    """AC1: a card with attempts, failure_class, and failure_role is parsed with all values."""
    raw = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 3,
        "failure_class": "parse",
        "failure_role": "Developer",
    }
    card = parse_card(raw)
    assert card.created == date(2024, 1, 1)
    assert card.started == date(2024, 1, 3)
    assert card.completed == date(2024, 1, 7)
    assert card.attempts == 3
    assert card.failure_class == "parse"
    assert card.failure_role == "Developer"


def test_parse_card_defaults_for_missing_new_fields():
    """AC2: a card without the new keys gets attempts 1, failure_class None, failure_role None."""
    raw = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    card = parse_card(raw)
    assert card.attempts == 1
    assert card.failure_class is None
    assert card.failure_role is None


def test_parse_card_zero_attempts_raises_value_error():
    """AC3: a card with attempts 0 raises ValueError mentioning 'attempts'."""
    raw = {"created": "2024-01-01", "attempts": 0}
    with pytest.raises(ValueError, match="attempts"):
        parse_card(raw)


def test_parse_card_partial_failure_fields():
    """AC4: a card with attempts and failure_class but no failure_role."""
    raw = {"created": "2024-01-01", "attempts": 2, "failure_class": "edit"}
    card = parse_card(raw)
    assert card.attempts == 2
    assert card.failure_class == "edit"
    assert card.failure_role is None


def test_parse_card_reads_points():
    """AC6: parse_card reads points from the input; missing points gives None."""
    from sprint_metrics.card import parse_card

    card = parse_card({"created": "2024-01-01", "points": 5, "attempts": 1})
    assert card.points == 5
    card_no_points = parse_card({"created": "2024-01-01", "attempts": 1})
    assert card_no_points.points is None


def test_parse_card_superseded_sponsor():
    """AC1: a card with superseded true and superseded_because 'sponsor' parses with both fields set."""
    raw = {
        "created": "2024-01-01",
        "superseded": True,
        "superseded_because": "sponsor",
        "points": 5,
    }
    card = parse_card(raw)
    assert card.superseded is True
    assert card.superseded_because == "sponsor"
    assert card.points == 5


def test_parse_card_superseded_story_problem():
    """AC2: a card with superseded true and superseded_because 'story_problem' parses correctly."""
    raw = {
        "created": "2024-01-01",
        "superseded": True,
        "superseded_because": "story_problem",
    }
    card = parse_card(raw)
    assert card.superseded is True
    assert card.superseded_because == "story_problem"


def test_parse_card_no_superseded_defaults():
    """AC3: a card without the superseded field gets superseded False and superseded_because None."""
    raw = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    card = parse_card(raw)
    assert card.superseded is False
    assert card.superseded_because is None


def test_parse_card_superseded_missing_because():
    """AC4: a card with superseded true but no superseded_because raises ValueError naming the field."""
    raw = {"created": "2024-01-01", "superseded": True}
    with pytest.raises(ValueError, match="superseded_because"):
        parse_card(raw)


def test_parse_card_superseded_invalid_because():
    """AC5: a card with superseded true and an invalid superseded_because raises ValueError naming the value."""
    raw = {"created": "2024-01-01", "superseded": True, "superseded_because": "frobnicated"}
    with pytest.raises(ValueError, match="frobnicated"):
        parse_card(raw)


def test_parse_card_datetime_only_fields():
    """AC1: a card with only _at datetime keys parses to aware UTC datetimes,
    leaving the date-only fields None."""
    card = parse_card(
        {
            "created_at": "2024-01-03T09:15:00Z",
            "started_at": "2024-01-03T10:00:00Z",
            "completed_at": "2024-01-03T21:26:00Z",
        }
    )
    assert card.created_at == datetime(2024, 1, 3, 9, 15, tzinfo=UTC)
    assert card.started_at == datetime(2024, 1, 3, 10, 0, tzinfo=UTC)
    assert card.completed_at == datetime(2024, 1, 3, 21, 26, tzinfo=UTC)
    assert card.created is None
    assert card.started is None
    assert card.completed is None


def test_parse_card_date_only_leaves_datetime_fields_none():
    """AC2: a card with only date keys leaves created_at/started_at/completed_at None."""
    card = parse_card({"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"})
    assert card.created == date(2024, 1, 1)
    assert card.started == date(2024, 1, 3)
    assert card.completed == date(2024, 1, 7)
    assert card.created_at is None
    assert card.started_at is None
    assert card.completed_at is None


def test_parse_card_invalid_created_at_raises():
    """AC3: an unparseable created_at raises ValueError naming 'created_at'."""
    with pytest.raises(ValueError, match="created_at"):
        parse_card({"created_at": "not-a-datetime"})


def test_parse_card_mixed_date_and_datetime_fields():
    """AC4: date fields and present _at fields parse together; absent completed_at stays None."""
    card = parse_card(
        {
            "created": "2024-01-01",
            "started": "2024-01-03",
            "completed": "2024-01-07",
            "created_at": "2024-01-01T08:00:00Z",
            "started_at": "2024-01-03T09:00:00Z",
        }
    )
    assert card.created == date(2024, 1, 1)
    assert card.started == date(2024, 1, 3)
    assert card.completed == date(2024, 1, 7)
    assert card.created_at == datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    assert card.started_at == datetime(2024, 1, 3, 9, 0, tzinfo=UTC)
    assert card.completed_at is None


def test_parse_card_with_failures_list():
    """AC1: a card with attempts 3 and a failures array of two objects parses
    with the failures in input order; first-attempt status is still decided
    solely by attempts."""
    raw = {
        "created": "2024-01-01",
        "started": "2024-01-01",
        "completed": "2024-01-03",
        "attempts": 3,
        "failures": [
            {"failure_class": "VERIFY", "failure_role": "Review"},
            {"failure_class": "SCHEMA", "failure_role": "QA"},
        ],
    }
    card = parse_card(raw)
    assert card.attempts == 3
    assert card.failures == [("VERIFY", "Review"), ("SCHEMA", "QA")]
    # First-attempt rate still based solely on attempts
    from sprint_metrics.metrics import calculate_first_attempt_rate

    cards = [card, Card(created=date(2024, 1, 1), completed=date(2024, 1, 2))]
    assert calculate_first_attempt_rate(cards) == 50


def test_cli_exits_zero_with_completed_card_carrying_failures(tmp_path, capsys):
    """AC1: the CLI exits 0 when run on a file whose one completed card carries
    attempts 3 and a failures array of two objects."""
    import json

    from sprint_metrics.cli import main

    cards = [
        {
            "created": "2024-01-01",
            "started": "2024-01-01",
            "completed": "2024-01-03",
            "attempts": 3,
            "failures": [
                {"failure_class": "VERIFY", "failure_role": "Review"},
                {"failure_class": "SCHEMA", "failure_role": "QA"},
            ],
        }
    ]
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    assert exit_code == 0


def test_parse_card_failures_absent_defaults_none():
    """AC2: a card with no 'failures' key gets failures=None."""
    raw = {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-05"}
    card = parse_card(raw)
    assert card.failures is None


def test_parse_card_failures_is_string_raises():
    """AC3: a card whose 'failures' value is a JSON string raises ValueError
    naming 'failures'."""
    raw = {"created": "2024-01-01", "failures": "not-an-array"}
    with pytest.raises(ValueError, match="failures"):
        parse_card(raw)


def test_cli_exits_2_on_invalid_failures(tmp_path, capsys):
    """AC3: the CLI exits 2 when a card's 'failures' value is a string, and
    stderr names the 'failures' field."""
    import json

    from sprint_metrics.cli import main

    cards = [
        {
            "created": "2024-01-01",
            "completed": "2024-01-03",
            "failures": "not-an-array",
        }
    ]
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "failures" in captured.err


def test_parse_card_failures_entry_missing_failure_role():
    """AC3: a failures entry missing 'failure_role' raises ValueError naming 'failures'."""
    raw = {"created": "2024-01-01", "failures": [{"failure_class": "VERIFY"}]}
    with pytest.raises(ValueError, match="failures"):
        parse_card(raw)


def test_parse_card_failures_entry_not_dict():
    """AC3: a failures entry that is not an object raises ValueError naming 'failures'."""
    raw = {"created": "2024-01-01", "failures": ["just-a-string"]}
    with pytest.raises(ValueError, match="failures"):
        parse_card(raw)


def test_parse_card_failures_error_states_expected_shape():
    """AC7: the error message states the shape it expects — an array of objects,
    each carrying string 'failure_class' and 'failure_role'."""
    raw = {"created": "2024-01-01", "failures": "not-an-array"}
    with pytest.raises(
        ValueError, match=r"failures.*array of objects.*failure_class.*failure_role"
    ):
        parse_card(raw)


def test_card_attempts_field_docstring():
    """AC4: the Card.attempts field carries a docstring that reads as
    'hands to review or QA (default: 1)'."""
    import inspect

    source = inspect.getsource(Card)
    assert "hands to review or QA" in source
    assert "attempts" in source
