"""Postgres persistence layer for the sprint-metrics service.

All SQL lives here; the service and CLI never construct queries directly.
The connection string is read from SPRINT_METRICS_DB.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sprint_metrics.card import Card

if TYPE_CHECKING:
    from psycopg import Connection

_DDL = """\
CREATE SCHEMA IF NOT EXISTS sprint_metrics;
CREATE TABLE IF NOT EXISTS sprint_metrics.board_events (
    card_id TEXT NOT NULL,
    type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    sprint TEXT NOT NULL,
    card_created DATE NOT NULL,
    attempts INT,
    failure_class TEXT,
    failure_role TEXT,
    PRIMARY KEY (card_id, type, event_time),
    CHECK (type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated'))
);
"""


def init_db(conn: Connection) -> None:
    """Create the sprint_metrics schema and board_events table if they do not exist."""
    conn.execute(_DDL)
    conn.commit()


def insert_event(conn: Connection, event: dict) -> None:
    """Insert a board event, doing nothing if it already exists (idempotent upsert).

    The event dict must have keys: card_id, type, timestamp, sprint, card (with 'created').
    Optional card fields: attempts, failure_class, failure_role (stored only on 'finished' rows).
    """
    card = event.get("card", {})
    event_type = event["type"]
    is_finished = event_type == "finished"

    conn.execute(
        """
        INSERT INTO sprint_metrics.board_events
            (card_id, type, event_time, sprint, card_created, attempts, failure_class, failure_role)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (card_id, type, event_time) DO NOTHING
        """,
        (
            event["card_id"],
            event_type,
            event["timestamp"],
            event["sprint"],
            card["created"],
            card.get("attempts") if is_finished else None,
            card.get("failure_class") if is_finished else None,
            card.get("failure_role") if is_finished else None,
        ),
    )
    conn.commit()


def query_sprint(conn: Connection, label: str) -> list[Card]:
    """Reconstruct Card objects for all cards whose 'finished' event has sprint=label.

    For each card_id, reconstructs:
    - created: from card_created (any row)
    - started: event_time date of the 'started' row
    - completed: event_time date of the 'finished' row
    - blocked_since: event_time date of the most recent 'blocked' row with no later 'unblocked'
    - attempts: from the 'finished' row (default 1)
    - failure_class/failure_role: from the 'finished' row
    """
    rows = conn.execute(
        """
        SELECT DISTINCT card_id FROM sprint_metrics.board_events
        WHERE type = 'finished' AND sprint = %s
        """,
        (label,),
    ).fetchall()

    if not rows:
        return []

    cards: list[Card] = []
    for (card_id,) in rows:
        events = conn.execute(
            """
            SELECT type, event_time, card_created, attempts, failure_class, failure_role
            FROM sprint_metrics.board_events
            WHERE card_id = %s
            ORDER BY event_time
            """,
            (card_id,),
        ).fetchall()

        card = _reconstruct_card(events)
        if card is not None:
            cards.append(card)

    return cards


def _reconstruct_card(events: list[tuple]) -> Card | None:
    """Reconstruct a Card from its stored events."""
    if not events:
        return None

    created: date | None = None
    started: date | None = None
    completed: date | None = None
    attempts = 1
    failure_class: str | None = None
    failure_role: str | None = None

    blocked_events: list[date] = []
    unblocked_events: list[date] = []

    for (
        event_type,
        event_time,
        card_created,
        ev_attempts,
        ev_failure_class,
        ev_failure_role,
    ) in events:
        event_date = event_time.date() if hasattr(event_time, "date") else event_time
        if created is None and card_created is not None:
            created = card_created
        if event_type == "started" and started is None:
            started = event_date
        elif event_type == "finished":
            completed = event_date
            if ev_attempts is not None:
                attempts = ev_attempts
            failure_class = ev_failure_class
            failure_role = ev_failure_role
        elif event_type == "blocked":
            blocked_events.append(event_date)
        elif event_type == "unblocked":
            unblocked_events.append(event_date)

    blocked_since: date | None = None
    if blocked_events:
        latest_blocked = max(blocked_events)
        has_later_unblock = any(u > latest_blocked for u in unblocked_events)
        if not has_later_unblock:
            blocked_since = latest_blocked

    if created is None:
        return None

    return Card(
        created=created,
        started=started,
        completed=completed,
        blocked_since=blocked_since,
        attempts=attempts,
        failure_class=failure_class,
        failure_role=failure_role,
    )


def health_check(conn: Connection) -> bool:
    """Return True if the database is reachable (SELECT 1 succeeds)."""
    import psycopg

    try:
        conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False
