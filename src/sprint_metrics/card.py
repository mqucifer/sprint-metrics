"""Card dataclass and card parsing for the sprint-metrics package."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Card:
    """A single card on the sprint board.

    ``started`` and ``completed`` are ``None`` while the card has not yet
    reached that point on the board.
    """

    created: date
    started: date | None = None
    completed: date | None = None
    blocked_since: date | None = None

    @property
    def is_completed(self) -> bool:
        """Whether the card has finished, and so counts towards the metrics."""
        return self.completed is not None

    @property
    def cycle_time(self) -> int:
        """Days from starting work to completing it, or 0 if either is missing."""
        if self.completed is None or self.started is None:
            return 0
        return (self.completed - self.started).days

    @property
    def lead_time(self) -> int:
        """Days from creation to completion, or 0 if the card is not complete."""
        if self.completed is None:
            return 0
        return (self.completed - self.created).days


def _parse_date(value: object, field: str) -> date | None:
    """Read an optional ISO-8601 date. Missing, null and empty all mean "not yet"."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO-8601 date string, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not an ISO-8601 date: {value!r}") from exc


def parse_card(raw: Mapping[str, object]) -> Card:
    """Build a ``Card`` from its serialised form."""
    created = _parse_date(raw.get("created"), "created")
    if created is None:
        raise ValueError("every card needs a 'created' date")
    return Card(
        created=created,
        started=_parse_date(raw.get("started"), "started"),
        completed=_parse_date(raw.get("completed"), "completed"),
        blocked_since=_parse_date(raw.get("blocked_since"), "blocked_since"),
    )


def _as_cards(cards: Iterable[Card | Mapping[str, object]]) -> list[Card]:
    """Accept cards either already parsed or still in their serialised form."""
    return [card if isinstance(card, Card) else parse_card(card) for card in cards]


def _load_cards(source: str) -> list[Card]:
    """Parse the JSON list of cards the command was given."""
    raw = json.loads(source) if source.strip() else []
    if not isinstance(raw, list):
        raise TypeError("expected a JSON list of cards")
    return _as_cards(raw)
