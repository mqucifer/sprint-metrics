"""Tests for the Card dataclass and card parsing in sprint_metrics.card."""

from datetime import date

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
