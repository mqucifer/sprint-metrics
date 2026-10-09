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
    attempt_number INT,
    points INT,
    PRIMARY KEY (card_id, type, event_time),
    CONSTRAINT board_events_type_check CHECK (
        type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated', 'attempt_failed')
    )
);
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS attempt_number INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS points INT;
ALTER TABLE sprint_metrics.board_events DROP CONSTRAINT IF EXISTS board_events_type_check;
ALTER TABLE sprint_metrics.board_events ADD CONSTRAINT board_events_type_check CHECK (
    type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated', 'attempt_failed')
);
CREATE TABLE IF NOT EXISTS sprint_metrics.sprints (
    name TEXT PRIMARY KEY,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    timezone TEXT NOT NULL
);
"""


def init_db(conn: Connection) -> None:
    """Create the sprint_metrics schema and board_events table if they do not exist."""
    conn.execute(_DDL)
    conn.commit()


def insert_event(conn: Connection, event: dict) -> None:
    """Insert a board event, doing nothing if it already exists (idempotent upsert).

    The event dict must have keys: card_id, type, timestamp, sprint, card (with 'created').
    Optional card fields: attempts, failure_class, failure_role (stored only on 'finished' rows),
    points (stored on every event row that carries it; NULL when absent).
    Optional top-level fields: attempt_number, failure_class, failure_role
    (stored only on 'attempt_failed' rows).
    """
    card = event.get("card", {})
    event_type = event["type"]
    is_finished = event_type == "finished"
    is_attempt_failed = event_type == "attempt_failed"

    if is_finished:
        ev_failure_class = card.get("failure_class")
        ev_failure_role = card.get("failure_role")
        ev_attempt_number = None
    elif is_attempt_failed:
        ev_failure_class = event.get("failure_class")
        ev_failure_role = event.get("failure_role")
        ev_attempt_number = event.get("attempt_number")
    else:
        ev_failure_class = None
        ev_failure_role = None
        ev_attempt_number = None

    conn.execute(
        """
        INSERT INTO sprint_metrics.board_events
            (card_id, type, event_time, sprint, card_created,
             attempts, failure_class, failure_role, attempt_number, points)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (card_id, type, event_time) DO NOTHING
        """,
        (
            event["card_id"],
            event_type,
            event["timestamp"],
            event["sprint"],
            card["created"],
            card.get("attempts") if is_finished else None,
            ev_failure_class,
            ev_failure_role,
            ev_attempt_number,
            card.get("points"),
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
    """Reconstruct a Card from its stored events.

    The card's attempts count is derived from the number of 'attempt_failed'
    rows in its history (1 + count) when any exist; otherwise it falls back
    to the attempts column on the 'finished' row (default 1).
    """
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
    attempt_failed_count = 0

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
        elif event_type == "attempt_failed":
            attempt_failed_count += 1

    if attempt_failed_count > 0:
        attempts = 1 + attempt_failed_count

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


def query_range(conn: Connection, start: str, end: str) -> dict[str, list[Card]]:
    """Reconstruct Card objects for each sprint label in the inclusive range start..end.

    Returns a dict mapping each label to its list of Card objects, in chronological order.
    """
    start_year, start_month = int(start[:4]), int(start[5:7])
    end_year, end_month = int(end[:4]), int(end[5:7])

    result: dict[str, list[Card]] = {}
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        label = f"{year:04d}-{month:02d}"
        result[label] = query_sprint(conn, label)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return result


def query_all_sprints(conn: Connection) -> dict[str, list[Card]]:
    """Reconstruct Card objects for each sprint that has at least one 'finished' event.

    Returns a dict mapping each sprint label to its list of Card objects,
    in chronological order.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT sprint FROM sprint_metrics.board_events
        WHERE type = 'finished'
        ORDER BY sprint
        """
    ).fetchall()

    result: dict[str, list[Card]] = {}
    for (sprint,) in rows:
        result[sprint] = query_sprint(conn, sprint)
    return result


def upsert_sprint(
    conn: Connection,
    name: str,
    start_date: date,
    end_date: date,
    timezone: str,
) -> None:
    """Insert or update a sprint definition by name."""
    conn.execute(
        """
        INSERT INTO sprint_metrics.sprints (name, start_date, end_date, timezone)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            timezone = EXCLUDED.timezone
        """,
        (name, start_date, end_date, timezone),
    )
    conn.commit()


def resolve_sprint_range(conn: Connection, start: str, end: str) -> list[str] | None:
    """Resolve a sprint range by registered start dates.

    Returns an ordered list of sprint names (by start_date) if both `start` and `end`
    exist in the sprints table with start.start_date <= end.start_date.
    Returns None if either label is not in the sprints table.
    Raises ValueError if start.start_date > end.start_date.
    """
    rows = conn.execute(
        """
        SELECT name, start_date FROM sprint_metrics.sprints
        WHERE name IN (%s, %s)
        """,
        (start, end),
    ).fetchall()

    if len(rows) < 2:
        return None

    by_name = {name: sd for name, sd in rows}
    start_date = by_name[start]
    end_date = by_name[end]

    if start_date > end_date:
        raise ValueError(f"invalid range: start {start!r} is after end {end!r}")

    ordered = conn.execute(
        """
        SELECT name FROM sprint_metrics.sprints
        WHERE start_date BETWEEN %s AND %s
        ORDER BY start_date
        """,
        (start_date, end_date),
    ).fetchall()

    return [name for (name,) in ordered]


def sprint_has_events(conn: Connection, label: str) -> bool:
    """Return True if any row in board_events has sprint = label."""
    row = conn.execute(
        "SELECT 1 FROM sprint_metrics.board_events WHERE sprint = %s LIMIT 1",
        (label,),
    ).fetchone()
    return row is not None
