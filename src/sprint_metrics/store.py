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
    goal TEXT,
    kind TEXT,
    replaced_by JSONB,
    PRIMARY KEY (card_id, type, event_time),
    CONSTRAINT board_events_type_check CHECK (
        type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated', 'attempt_failed', 'superseded', 'returned')
    ),
    CONSTRAINT board_events_because_check CHECK (
        because IS NULL OR because IN ('sponsor', 'story_problem')
    )
);
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS attempt_number INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS points INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS because TEXT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS epic TEXT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS goal TEXT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS kind TEXT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS replaced_by JSONB;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS card_created_at TIMESTAMPTZ;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS model_seconds INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS input_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS cached_input_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS output_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS reasoning_output_tokens BIGINT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS model_time_split_refinement INT;
ALTER TABLE sprint_metrics.board_events ADD COLUMN IF NOT EXISTS model_time_split_delivery INT;
ALTER TABLE sprint_metrics.board_events DROP CONSTRAINT IF EXISTS board_events_type_check;
ALTER TABLE sprint_metrics.board_events ADD CONSTRAINT board_events_type_check CHECK (
    type IN ('started', 'blocked', 'unblocked', 'finished', 'escalated', 'attempt_failed', 'superseded', 'returned')
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
    created_at (stored on every event row that carries it; NULL when absent),
    kind (stored on every event row that carries it; NULL when absent).
    Optional top-level fields: attempt_number, failure_class, failure_role
    (stored only on 'attempt_failed' rows); failure_class and failure_role are
    also stored on 'returned' rows.
    Optional top-level fields: because, replaced_by (stored only on 'superseded' rows);
    epic and goal are stored on every event row that carries them; NULL when absent.

    On re-send (conflict on the primary key), NULL columns receive the new value;
    columns that already hold a value are left unchanged (epic R1).
    """
    card = event.get("card", {})
    event_type = event["type"]
    is_finished = event_type == "finished"
    is_attempt_failed = event_type == "attempt_failed"
    is_superseded = event_type == "superseded"
    is_returned = event_type == "returned"

    if is_finished:
        ev_failure_class = card.get("failure_class")
        ev_failure_role = card.get("failure_role")
        ev_attempt_number = None
    elif is_attempt_failed:
        ev_failure_class = event.get("failure_class")
        ev_failure_role = event.get("failure_role")
        ev_attempt_number = event.get("attempt_number")
    elif is_returned:
        ev_failure_class = event.get("failure_class")
        ev_failure_role = event.get("failure_role")
        ev_attempt_number = None
    else:
        ev_failure_class = None
        ev_failure_role = None
        ev_attempt_number = None

    ev_because = event.get("because") if is_superseded else None
    ev_epic = event.get("epic")
    ev_goal = event.get("goal")
    ev_kind = card.get("kind")
    ev_replaced_by = (
        json.dumps(event["replaced_by"]) if is_superseded and "replaced_by" in event else None
    )

    card_created_at = _parse_datetime(card.get("created_at"), "created_at")

    ev_model_seconds = card.get("model_seconds") if is_finished else None
    ev_input_tokens = card.get("input_tokens") if is_finished else None
    ev_cached_input_tokens = card.get("cached_input_tokens") if is_finished else None
    ev_output_tokens = card.get("output_tokens") if is_finished else None
    ev_reasoning_output_tokens = card.get("reasoning_output_tokens") if is_finished else None

    ev_model_time_split_refinement = None
    ev_model_time_split_delivery = None
    if is_finished:
        split = card.get("model_time_split")
        if isinstance(split, dict):
            ev_model_time_split_refinement = split.get("refinement")
            ev_model_time_split_delivery = split.get("delivery")

    conn.execute(
        """
        INSERT INTO sprint_metrics.board_events
            (card_id, type, event_time, sprint, card_created,
             attempts, failure_class, failure_role, attempt_number, points,
             because, epic, goal, kind, replaced_by, card_created_at,
             model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
             model_time_split_refinement, model_time_split_delivery)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (card_id, type, event_time) DO UPDATE SET
            attempts = COALESCE(board_events.attempts, EXCLUDED.attempts),
            failure_class = COALESCE(board_events.failure_class, EXCLUDED.failure_class),
            failure_role = COALESCE(board_events.failure_role, EXCLUDED.failure_role),
            attempt_number = COALESCE(board_events.attempt_number, EXCLUDED.attempt_number),
            points = COALESCE(board_events.points, EXCLUDED.points),
            because = COALESCE(board_events.because, EXCLUDED.because),
            epic = COALESCE(board_events.epic, EXCLUDED.epic),
            goal = COALESCE(board_events.goal, EXCLUDED.goal),
            kind = COALESCE(board_events.kind, EXCLUDED.kind),
            replaced_by = COALESCE(board_events.replaced_by, EXCLUDED.replaced_by),
            card_created_at = COALESCE(board_events.card_created_at, EXCLUDED.card_created_at),
            model_seconds = COALESCE(board_events.model_seconds, EXCLUDED.model_seconds),
            input_tokens = COALESCE(board_events.input_tokens, EXCLUDED.input_tokens),
            cached_input_tokens = COALESCE(board_events.cached_input_tokens, EXCLUDED.cached_input_tokens),
            output_tokens = COALESCE(board_events.output_tokens, EXCLUDED.output_tokens),
            reasoning_output_tokens = COALESCE(board_events.reasoning_output_tokens, EXCLUDED.reasoning_output_tokens),
            model_time_split_refinement = COALESCE(board_events.model_time_split_refinement, EXCLUDED.model_time_split_refinement),
            model_time_split_delivery = COALESCE(board_events.model_time_split_delivery, EXCLUDED.model_time_split_delivery)
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
            ev_goal,
            ev_kind,
            ev_replaced_by,
            card_created_at,
            ev_model_seconds,
            ev_input_tokens,
            ev_cached_input_tokens,
            ev_output_tokens,
            ev_reasoning_output_tokens,
            ev_model_time_split_refinement,
            ev_model_time_split_delivery,
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
        if ev_points is not None and (event_type == "finished" or points is None):
            points = ev_points
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
            model_seconds = ev_model_seconds
            input_tokens = ev_input_tokens
            cached_input_tokens = ev_cached_input_tokens
            output_tokens = ev_output_tokens
            reasoning_output_tokens = ev_reasoning_output_tokens
        elif event_type == "superseded":
            superseded = True
            superseded_because = ev_because
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


def query_started_count(conn: Connection, label: str) -> int:
    """Return the number of distinct stories with a 'started' event in the sprint."""
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT card_id) FROM sprint_metrics.board_events
        WHERE type = 'started' AND sprint = %s
        """,
        (label,),
    ).fetchone()
    return row[0]


def query_returned_events(
    conn: Connection, label: str
) -> list[tuple[str, str | None, str | None]]:
    """Return the sprint's 'returned' rows as (card_id, step, reason), in event order.

    step is the failure_role the crew sent (the role that sent the story back)
    and reason the failure_class (the reason for the send-back); each is None
    when the crew did not send it.
    """
    rows = conn.execute(
        """
        SELECT card_id, failure_role, failure_class
        FROM sprint_metrics.board_events
        WHERE type = 'returned' AND sprint = %s
        ORDER BY event_time
        """,
        (label,),
    ).fetchall()
    return [(card_id, failure_role, failure_class) for card_id, failure_role, failure_class in rows]


def query_working_time_events(
    conn: Connection, label: str
) -> dict[str, list[tuple[str, datetime, str | None]]]:
    """Return the sprint's session rows for working-time computation, grouped by card.

    For each card_id, the ordered list of (event_type, event_time, failure_role)
    over its 'started', 'finished', 'attempt_failed', 'returned', 'blocked', and
    'unblocked' rows in the sprint, in event order. failure_role is None unless
    the row is an 'attempt_failed' or 'returned' row that carried one.
    """
    rows = conn.execute(
        """
        SELECT card_id, type, event_time, failure_role
        FROM sprint_metrics.board_events
        WHERE sprint = %s
          AND type IN ('started', 'finished', 'attempt_failed', 'returned', 'blocked', 'unblocked')
        ORDER BY card_id, event_time
        """,
        (label,),
    ).fetchall()
    result: dict[str, list[tuple[str, datetime, str | None]]] = {}
    for card_id, event_type, event_time, failure_role in rows:
        result.setdefault(card_id, []).append((event_type, event_time, failure_role))
    return result


def query_card_kinds(conn: Connection, label: str) -> dict[str, str | None]:
    """Return the sprint's story kinds, keyed by card_id.

    For each card_id that appears in the sprint's board_events, the kind stored
    on any of its rows (the kind is the same on every row that carries it), or
    None when no row for that card carries a kind.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT ON (card_id) card_id, kind
        FROM sprint_metrics.board_events
        WHERE sprint = %s
        ORDER BY card_id, (kind IS NULL), event_time
        """,
        (label,),
    ).fetchall()
    result: dict[str, str | None] = {}
    for card_id, kind in rows:
        result[card_id] = kind
    return result


def query_roster_data(conn: Connection, labels: list[str]) -> dict:
    """Return the roster data for the given sprint labels.

    Computes from stored 'finished' events only:
    - completed stories per sprint (deduplicated card_ids)
    - the sprint where each epic releases (the sprint of its last story's finished event)
    - the sprint where each goal is achieved (the sprint where its last epic releases)
    - which sprints carry at least one finished event with an epic link
    - which sprints carry at least one finished event with a goal link

    Returns a dict with keys: 'completed', 'released_epics', 'achieved_goals',
    'sprints_with_epic', 'sprints_with_goal'.
    """
    placeholders = ",".join(["%s"] * len(labels))
    rows = conn.execute(
        f"""
        SELECT card_id, sprint, event_time, epic, goal
        FROM sprint_metrics.board_events
        WHERE type = 'finished' AND sprint IN ({placeholders})
        ORDER BY event_time
        """,
        labels,
    ).fetchall()

    completed: dict[str, list[str]] = {label: [] for label in labels}
    sprints_with_epic: set[str] = set()
    sprints_with_goal: set[str] = set()
    epic_latest: dict[str, tuple] = {}  # epic -> (event_time, sprint)
    goal_epics: dict[str, list] = {}  # goal -> [(event_time, sprint)]

    for card_id, sprint, event_time, epic, goal in rows:
        if sprint in completed:
            completed[sprint].append(card_id)
        if epic is not None:
            sprints_with_epic.add(sprint)
            if epic not in epic_latest or event_time > epic_latest[epic][0]:
                epic_latest[epic] = (event_time, sprint)
        if goal is not None:
            sprints_with_goal.add(sprint)
            if goal not in goal_epics:
                goal_epics[goal] = []
            goal_epics[goal].append((event_time, sprint))

    released_epics: dict[str, list[str]] = {label: [] for label in labels}
    for epic, (_event_time, sprint) in epic_latest.items():
        if sprint in released_epics:
            released_epics[sprint].append(epic)

    achieved_goals: dict[str, list[str]] = {label: [] for label in labels}
    for goal, entries in goal_epics.items():
        latest = max(entries, key=lambda x: x[0])
        achieved_sprint = latest[1]
        if achieved_sprint in achieved_goals:
            achieved_goals[achieved_sprint].append(goal)

    for label in labels:
        completed[label] = sorted(set(completed[label]))
        released_epics[label] = sorted(released_epics[label])
        achieved_goals[label] = sorted(achieved_goals[label])

    return {
        "completed": completed,
        "released_epics": released_epics,
        "achieved_goals": achieved_goals,
        "sprints_with_epic": sprints_with_epic,
        "sprints_with_goal": sprints_with_goal,
    }


def query_dora_data(conn: Connection, labels: list[str]) -> dict:
    """Return DORA computation data for the given sprint labels.

    Computes from stored 'finished' events that carry an epic link:
    - which epics release in each sprint (the epic's last story's finished
      event is the latest among the range)
    - for each released story, the span in days from its card's created date
      to the release moment (its epic's last story's finished event time)

    Returns a dict with keys:
    'released_epics': {sprint: [epic1, ...]} or None per sprint
    'story_spans_days': {sprint: [span1, ...]} or None per sprint
    'sprints_with_epic': set of sprints with at least one finished event carrying an epic
    """
    from datetime import datetime as dt

    placeholders = ",".join(["%s"] * len(labels))
    rows = conn.execute(
        f"""
        SELECT card_id, sprint, event_time, epic, card_created
        FROM sprint_metrics.board_events
        WHERE type = 'finished' AND epic IS NOT NULL AND sprint IN ({placeholders})
        ORDER BY event_time
        """,
        labels,
    ).fetchall()

    if not rows:
        return {
            "released_epics": {label: None for label in labels},
            "story_spans_days": {label: None for label in labels},
            "sprints_with_epic": set(),
        }

    epic_latest: dict[str, tuple] = {}
    sprints_with_epic: set[str] = set()
    for _card_id, sprint, event_time, epic, _card_created in rows:
        sprints_with_epic.add(sprint)
        if epic not in epic_latest or event_time > epic_latest[epic][0]:
            epic_latest[epic] = (event_time, sprint)

    released_epics: dict[str, list[str] | None] = {label: None for label in labels}
    for epic, (_event_time, sprint) in epic_latest.items():
        if sprint in released_epics:
            if released_epics[sprint] is None:
                released_epics[sprint] = []
            released_epics[sprint].append(epic)
    for label in labels:
        if released_epics[label] is not None:
            released_epics[label] = sorted(released_epics[label])

    story_spans_days: dict[str, list[float] | None] = {label: None for label in labels}
    for _card_id, sprint, _event_time, epic, card_created in rows:
        release_moment = epic_latest[epic][0]
        created_dt = dt(
            card_created.year, card_created.month, card_created.day,
            tzinfo=release_moment.tzinfo,
        )
        span_days = (release_moment - created_dt).total_seconds() / 86400
        if story_spans_days[sprint] is None:
            story_spans_days[sprint] = []
        story_spans_days[sprint].append(span_days)

    return {
        "released_epics": released_epics,
        "story_spans_days": story_spans_days,
        "sprints_with_epic": sprints_with_epic,
    }
