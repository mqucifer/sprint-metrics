"""Postgres persistence layer for the sprint-metrics service.

All SQL lives here; the service and CLI never construct queries directly.
The connection string is read from SPRINT_METRICS_DB.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import TYPE_CHECKING

from sprint_metrics.card import Card, _parse_datetime

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
    because TEXT,
    epic TEXT,
    replaced_by JSONB,
    PRIMARY KEY (card_id, type, event_time),
    CONSTRAINT board_events_type_check CHECK (
        type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated', 'attempt_failed', 'superseded')
    ),
    CONSTRAINT board_events_because_check CHECK (
        because IS NULL OR because IN ('sponsor', 'story_problem')
    )
);
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS attempt_number INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS points INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS because TEXT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS epic TEXT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS replaced_by JSONB;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS card_created_at TIMESTAMPTZ;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS model_seconds INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS input_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS cached_input_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS output_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS reasoning_output_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events DROP CONSTRAINT IF EXISTS board_events_type_check;
ALTER TABLE sprint_metrics.board_events ADD CONSTRAINT board_events_type_check CHECK (
    type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated', 'attempt_failed', 'superseded')
);
ALTER TABLE sprint_metrics.board_events DROP CONSTRAINT IF EXISTS board_events_because_check;
ALTER TABLE sprint_metrics.board_events ADD CONSTRAINT board_events_because_check CHECK (
    because IS NULL OR because IN ('sponsor', 'story_problem')
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
    """Insert a board event, filling NULL fields on re-send without overwriting set values.

    The event dict must have keys: card_id, type, timestamp, sprint, card (with 'created').
    Optional card fields: attempts, failure_class, failure_role (stored only on 'finished' rows),
    points (stored on every event row that carries it; NULL when absent),
    created_at (stored on every event row that carries it; NULL when absent).
    Optional top-level fields: attempt_number, failure_class, failure_role
    (stored only on 'attempt_failed' rows).
    Optional top-level fields: because, epic, replaced_by (stored only on 'superseded' rows).

    On re-send (conflict on the primary key), NULL columns receive the new value;
    columns that already hold a value are left unchanged (epic R1).
    """
    card = event.get("card", {})
    event_type = event["type"]
    is_finished = event_type == "finished"
    is_attempt_failed = event_type == "attempt_failed"
    is_superseded = event_type == "superseded"

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

    ev_because = event.get("because") if is_superseded else None
    ev_epic = event.get("epic") if is_superseded else None
    ev_replaced_by = (
        json.dumps(event["replaced_by"]) if is_superseded and "replaced_by" in event else None
    )

    card_created_at = _parse_datetime(card.get("created_at"), "created_at")

    ev_model_seconds = card.get("model_seconds") if is_finished else None
    ev_input_tokens = card.get("input_tokens") if is_finished else None
    ev_cached_input_tokens = card.get("cached_input_tokens") if is_finished else None
    ev_output_tokens = card.get("output_tokens") if is_finished else None
    ev_reasoning_output_tokens = card.get("reasoning_output_tokens") if is_finished else None

    conn.execute(
        """
        INSERT INTO sprint_metrics.board_events
            (card_id, type, event_time, sprint, card_created,
             attempts, failure_class, failure_role, attempt_number, points,
             because, epic, replaced_by, card_created_at,
             model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (card_id, type, event_time) DO UPDATE SET
            attempts = COALESCE(board_events.attempts, EXCLUDED.attempts),
            failure_class = COALESCE(board_events.failure_class, EXCLUDED.failure_class),
            failure_role = COALESCE(board_events.failure_role, EXCLUDED.failure_role),
            attempt_number = COALESCE(board_events.attempt_number, EXCLUDED.attempt_number),
            points = COALESCE(board_events.points, EXCLUDED.points),
            because = COALESCE(board_events.because, EXCLUDED.because),
            epic = COALESCE(board_events.epic, EXCLUDED.epic),
            replaced_by = COALESCE(board_events.replaced_by, EXCLUDED.replaced_by),
            card_created_at = COALESCE(board_events.card_created_at, EXCLUDED.card_created_at),
            model_seconds = COALESCE(board_events.model_seconds, EXCLUDED.model_seconds),
            input_tokens = COALESCE(board_events.input_tokens, EXCLUDED.input_tokens),
            cached_input_tokens = COALESCE(board_events.cached_input_tokens, EXCLUDED.cached_input_tokens),
            output_tokens = COALESCE(board_events.output_tokens, EXCLUDED.output_tokens),
            reasoning_output_tokens = COALESCE(board_events.reasoning_output_tokens, EXCLUDED.reasoning_output_tokens)
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
            ev_because,
            ev_epic,
            ev_replaced_by,
            card_created_at,
            ev_model_seconds,
            ev_input_tokens,
            ev_cached_input_tokens,
            ev_output_tokens,
            ev_reasoning_output_tokens,
        ),
    )
    conn.commit()


def query_sprint(conn: Connection, label: str) -> list[Card]:
    """Reconstruct Card objects for all cards that finished or were superseded in the sprint.

    A card is included when it has a 'finished' or a 'superseded' row with
    sprint=label. For each card_id, reconstructs:
    - created: from card_created (any row)
    - created_at: from card_created_at (first non-NULL row)
    - started: event_time date of the 'started' row
    - started_at: event_time of the 'started' row (full TIMESTAMPTZ)
    - completed: event_time date of the 'finished' row
    - completed_at: event_time of the 'finished' row (full TIMESTAMPTZ)
    - blocked_since: event_time date of the most recent 'blocked' row with no later 'unblocked'
    - attempts: from the 'finished' row (default 1)
    - failure_class/failure_role: from the 'finished' row
    - points: from the 'finished' row, or the 'superseded' row when there is no 'finished' row
    - superseded / superseded_because: from the 'superseded' row
    """
    rows = conn.execute(
        """
        SELECT DISTINCT card_id FROM sprint_metrics.board_events
        WHERE (type = 'finished' OR type = 'superseded') AND sprint = %s
        """,
        (label,),
    ).fetchall()

    if not rows:
        return []

    cards: list[Card] = []
    for (card_id,) in rows:
        events = conn.execute(
            """
            SELECT type, event_time, card_created, card_created_at, attempts,
                   failure_class, failure_role, points, because,
                   model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens
            FROM sprint_metrics.board_events
            WHERE card_id = %s
            ORDER BY event_time
            """,
            (card_id,),
        ).fetchall()

        card = _reconstruct_card(events, card_id)
        if card is not None:
            cards.append(card)

    return cards


def _reconstruct_card(events: list[tuple], card_id: str | None = None) -> Card | None:
    """Reconstruct a Card from its stored events.

    The card's attempts count takes the crew-sent attempts from the 'finished'
    row when that column is non-NULL; otherwise it falls back to 1 plus the
    number of 'attempt_failed' rows; otherwise it defaults to 1.
    The failures list is built from the (failure_class, failure_role) of each
    'attempt_failed' row; the 'finished' row's failure fields populate
    Card.failure_class/failure_role for display but do not add an entry to
    the failures list.
    Points are read from the 'finished' row, or from the 'superseded' row when
    there is no 'finished' row. A 'superseded' row sets the card's superseded
    flag and superseded_because from the row's because column.
    The card_created_at column (TIMESTAMPTZ) is read from the first non-NULL row
    and assigned to the Card's created_at field. The full event_time (TIMESTAMPTZ)
    is assigned to started_at and completed_at.
    The five cost columns (model_seconds, input_tokens, cached_input_tokens,
    output_tokens, reasoning_output_tokens) are read from the 'finished' row
    and assigned to the Card's cost fields. The card_id is assigned to the
    Card's card_id field.
    """
    if not events:
        return None

    created: date | None = None
    created_at: datetime | None = None
    started: date | None = None
    started_at: datetime | None = None
    completed: date | None = None
    completed_at: datetime | None = None
    attempts = 1
    failure_class: str | None = None
    failure_role: str | None = None
    points: int | None = None
    superseded = False
    superseded_because: str | None = None
    model_seconds: int | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    blocked_events: list[date] = []
    unblocked_events: list[date] = []
    attempt_failed_count = 0
    finished_attempts: int | None = None
    failures: list[tuple[str, str]] = []

    for row in events:
        (
            event_type,
            event_time,
            card_created,
            card_created_at,
            ev_attempts,
            ev_failure_class,
            ev_failure_role,
            ev_points,
            ev_because,
        ) = row[:9]
        ev_model_seconds = row[9] if len(row) > 9 else None
        ev_input_tokens = row[10] if len(row) > 10 else None
        ev_cached_input_tokens = row[11] if len(row) > 11 else None
        ev_output_tokens = row[12] if len(row) > 12 else None
        ev_reasoning_output_tokens = row[13] if len(row) > 13 else None
        event_date = event_time.date() if hasattr(event_time, "date") else event_time
        if created is None and card_created is not None:
            created = card_created
        if created_at is None and card_created_at is not None:
            created_at = card_created_at
        if event_type == "started" and started is None:
            started = event_date
            started_at = event_time
        elif event_type == "finished":
            completed = event_date
            completed_at = event_time
            finished_attempts = ev_attempts
            failure_class = ev_failure_class
            failure_role = ev_failure_role
            points = ev_points
            model_seconds = ev_model_seconds
            input_tokens = ev_input_tokens
            cached_input_tokens = ev_cached_input_tokens
            output_tokens = ev_output_tokens
            reasoning_output_tokens = ev_reasoning_output_tokens
        elif event_type == "superseded":
            superseded = True
            superseded_because = ev_because
            if points is None:
                points = ev_points
        elif event_type == "blocked":
            blocked_events.append(event_date)
        elif event_type == "unblocked":
            unblocked_events.append(event_date)
        elif event_type == "attempt_failed":
            attempt_failed_count += 1
            failures.append((ev_failure_class or "", ev_failure_role or ""))

    if finished_attempts is not None:
        attempts = finished_attempts
    elif attempt_failed_count > 0:
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
        points=points,
        superseded=superseded,
        superseded_because=superseded_because,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        model_seconds=model_seconds,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        card_id=card_id,
        failures=failures or None,
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

    names_in_db = {name for (name, _) in rows}
    if start not in names_in_db or end not in names_in_db:
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


def count_escalated_events(conn: Connection, label: str) -> int:
    """Return the count of 'escalated' events stored for the given sprint label."""
    row = conn.execute(
        "SELECT COUNT(*) FROM sprint_metrics.board_events WHERE type = 'escalated' AND sprint = %s",
        (label,),
    ).fetchone()
    return row[0] if row else 0
