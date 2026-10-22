"""Card dataclass and card parsing for the sprint-metrics package."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class Card:
    """A single card on the sprint board.

    ``started`` and ``completed`` are ``None`` while the card has not yet
    reached that point on the board.
    """

    created: date | None
    started: date | None = None
    completed: date | None = None
    blocked_since: date | None = None
    attempts: int = 1  # hands to review or QA (default: 1)
    failure_class: str | None = None
    failure_role: str | None = None
    points: int | None = None
    superseded: bool = False
    superseded_because: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_seconds: int | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    card_id: str | None = None
    failures: list[tuple[str, str]] | None = None

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
    created_at = _parse_datetime(raw.get("created_at"), "created_at")
    if created is None and created_at is None:
        raise ValueError("every card needs a 'created' date or a 'created_at' timestamp")
    attempts = raw.get("attempts")
    if attempts is None:
        attempts = 1
    elif attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts!r}")
    points = raw.get("points")
    if points is not None:
        points = int(points)
    superseded = raw.get("superseded") is True
    superseded_because: str | None = None
    if superseded:
        reason = raw.get("superseded_because")
        if reason is None:
            raise ValueError("superseded_because is required when superseded is true")
        if reason not in ("sponsor", "story_problem"):
            raise ValueError(
                f"superseded_because must be 'sponsor' or 'story_problem', got {reason!r}"
            )
        superseded_because = reason
    failures_raw = raw.get("failures")
    failures: list[tuple[str, str]] | None = None
    if failures_raw is not None:
        if not isinstance(failures_raw, list):
            raise ValueError(
                "failures must be an array of objects, "
                "each carrying string 'failure_class' and 'failure_role'"
            )
        failures = []
        for entry in failures_raw:
            if not isinstance(entry, dict):
                raise ValueError(
                    "failures must be an array of objects, "
                    "each carrying string 'failure_class' and 'failure_role'"
                )
            fc = entry.get("failure_class")
            fr = entry.get("failure_role")
            if not isinstance(fc, str) or not isinstance(fr, str):
                raise ValueError(
                    "failures must be an array of objects, "
                    "each carrying string 'failure_class' and 'failure_role'"
                )
            failures.append((fc, fr))
    return Card(
        created=created,
        started=_parse_date(raw.get("started"), "started"),
        completed=_parse_date(raw.get("completed"), "completed"),
        blocked_since=_parse_date(raw.get("blocked_since"), "blocked_since"),
        attempts=attempts,
        failure_class=raw.get("failure_class"),
        failure_role=raw.get("failure_role"),
        points=points,
        superseded=superseded,
        superseded_because=superseded_because,
        created_at=created_at,
        started_at=_parse_datetime(raw.get("started_at"), "started_at"),
        completed_at=_parse_datetime(raw.get("completed_at"), "completed_at"),
        failures=failures,
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


def _parse_datetime(value: object, field: str) -> datetime | None:
    """Read an optional ISO-8601 datetime. Missing, null and empty all mean "not yet"."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 datetime string, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not an ISO-8601 datetime: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
