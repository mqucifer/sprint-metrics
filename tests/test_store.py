"""Tests for the store module against a live Postgres database.

Skips when SPRINT_METRICS_DB is not set.
"""

from __future__ import annotations

import os
from datetime import UTC, date

import pytest

try:
    import psycopg
except ImportError:
    psycopg = None

from sprint_metrics.metrics import calculate_superseded_points
from sprint_metrics.store import init_db, insert_event, query_sprint, upsert_sprint

DB_URL = os.environ.get("SPRINT_METRICS_DB")

pytestmark = pytest.mark.skipif(
    not DB_URL or psycopg is None,
    reason="SPRINT_METRICS_DB not set or psycopg unavailable",
)


@pytest.fixture()
def conn():
    connection = psycopg.connect(DB_URL)
    init_db(connection)
    connection.execute("DELETE FROM sprint_metrics.sprints")
    connection.commit()
    yield connection
    connection.close()


def test_sprints_table_exists_with_expected_columns(conn):
    rows = conn.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'sprints' AND table_schema = 'sprint_metrics'
        ORDER BY column_name
        """
    ).fetchall()
    column_names = [r[0] for r in rows]
    assert column_names == ["end_date", "name", "start_date", "timezone"]

    count = conn.execute("SELECT COUNT(*) FROM sprint_metrics.sprints").fetchone()[0]
    assert count == 0


def test_init_db_adds_the_cost_columns_to_a_table_from_before_them(conn):
    """A board_events table in the live service's 14-column shape (from before
    the cost fields) gains the cost columns, and keeps its rows, when init_db runs."""
    conn.execute("DROP TABLE sprint_metrics.board_events")
    conn.execute(
        """
        CREATE TABLE sprint_metrics.board_events (
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
            card_created_at TIMESTAMPTZ,
            PRIMARY KEY (card_id, type, event_time)
        )
        """
    )
    conn.execute(
        "INSERT INTO sprint_metrics.board_events (card_id, type, event_time, sprint, card_created) "
        "VALUES ('c_old', 'started', '2024-01-03T10:00:00Z', '2024-01', '2024-01-01')"
    )
    conn.commit()

    init_db(conn)

    rows = conn.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'board_events' AND table_schema = 'sprint_metrics'
        """
    ).fetchall()
    column_names = {r[0] for r in rows}
    assert {
        "model_seconds",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    } <= column_names
    assert len(column_names) == 23
    count = conn.execute("SELECT COUNT(*) FROM sprint_metrics.board_events").fetchone()[0]
    assert count == 1


def test_upsert_sprint_inserts_row(conn):
    upsert_sprint(conn, "Sprint 18", date(2026, 10, 7), date(2026, 10, 7), "America/Chicago")
    rows = conn.execute(
        "SELECT name, start_date, end_date, timezone FROM sprint_metrics.sprints ORDER BY name"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == ("Sprint 18", date(2026, 10, 7), date(2026, 10, 7), "America/Chicago")


def test_upsert_sprint_updates_existing_row(conn):
    upsert_sprint(conn, "Sprint 18", date(2024, 1, 15), date(2024, 2, 15), "UTC")
    upsert_sprint(conn, "Sprint 18", date(2024, 1, 20), date(2024, 2, 20), "America/New_York")
    rows = conn.execute(
        "SELECT name, start_date, end_date, timezone FROM sprint_metrics.sprints WHERE name = %s",
        ("Sprint 18",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == ("Sprint 18", date(2024, 1, 20), date(2024, 2, 20), "America/New_York")


def test_board_events_has_card_created_at_column(conn):
    """AC4: init_db creates card_created_at column as timestamp with time zone."""
    rows = conn.execute(
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'sprint_metrics' AND table_name = 'board_events'
        AND column_name = 'card_created_at'
        """
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "card_created_at"
    assert rows[0][1] == "timestamp with time zone"


def test_query_sprint_returns_superseded_card_with_because(conn):
    """AC1: a card with a superseded row and no finished row is returned superseded."""
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('Sprint 19', 'Sprint 20', 'Sprint 99')"
    )
    conn.commit()
    insert_event(
        conn,
        {
            "api_version": "1",
            "card_id": "sup19_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "Sprint 19",
            "card": {"created": "2024-01-02"},
            "because": "sponsor",
        },
    )
    cards = query_sprint(conn, "Sprint 19")
    assert len(cards) == 1
    assert cards[0].superseded is True
    assert cards[0].superseded_because == "sponsor"


def test_query_sprint_superseded_points(conn):
    """AC2: a superseded card's points flow through calculate_superseded_points."""
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('Sprint 19', 'Sprint 20', 'Sprint 99')"
    )
    conn.commit()
    insert_event(
        conn,
        {
            "api_version": "1",
            "card_id": "sup20_c1",
            "type": "superseded",
            "timestamp": "2024-02-04T10:00:00Z",
            "sprint": "Sprint 20",
            "card": {"created": "2024-02-02", "points": 5},
            "because": "story_problem",
        },
    )
    cards = query_sprint(conn, "Sprint 20")
    assert calculate_superseded_points(cards) == 5


def test_query_sprint_finished_card_not_superseded(conn):
    """AC3: a started+finished card with no superseded row is not superseded."""
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('Sprint 19', 'Sprint 20', 'Sprint 99')"
    )
    conn.commit()
    insert_event(
        conn,
        {
            "api_version": "1",
            "card_id": "s99_c1",
            "type": "started",
            "timestamp": "2024-03-03T10:00:00Z",
            "sprint": "Sprint 99",
            "card": {"created": "2024-03-02"},
        },
    )
    insert_event(
        conn,
        {
            "api_version": "1",
            "card_id": "s99_c1",
            "type": "finished",
            "timestamp": "2024-03-05T10:00:00Z",
            "sprint": "Sprint 99",
            "card": {"created": "2024-03-02"},
        },
    )
    cards = query_sprint(conn, "Sprint 99")
    assert len(cards) == 1
    assert cards[0].superseded is False
    assert cards[0].superseded_because is None


def test_upsert_fills_null_points_on_resend(conn):
    """AC1: re-sending an event with points fills a NULL points column."""
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_fill'")
    conn.commit()
    insert_event(
        conn,
        {
            "card_id": "c_fill",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
        },
    )
    insert_event(
        conn,
        {
            "card_id": "c_fill",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
        },
    )
    rows = conn.execute(
        "SELECT points FROM sprint_metrics.board_events "
        "WHERE card_id = 'c_fill' AND type = 'finished' AND event_time = '2024-01-07T15:00:00Z'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 5


def test_upsert_keeps_existing_points_on_resend(conn):
    """AC2: re-sending an event with a different points value does not overwrite a set column."""
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_keep'")
    conn.commit()
    insert_event(
        conn,
        {
            "card_id": "c_keep",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
        },
    )
    insert_event(
        conn,
        {
            "card_id": "c_keep",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 3},
        },
    )
    rows = conn.execute(
        "SELECT points FROM sprint_metrics.board_events "
        "WHERE card_id = 'c_keep' AND type = 'finished' AND event_time = '2024-01-07T15:00:00Z'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 5


def test_upsert_fills_null_card_created_at_on_resend(conn):
    """AC5: re-sending an event with card.created_at fills a NULL card_created_at column."""
    from datetime import datetime

    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_created'")
    conn.commit()
    insert_event(
        conn,
        {
            "card_id": "c_created",
            "type": "started",
            "timestamp": "2024-01-03T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
        },
    )
    insert_event(
        conn,
        {
            "card_id": "c_created",
            "type": "started",
            "timestamp": "2024-01-03T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "created_at": "2024-01-01T08:30:00Z"},
        },
    )
    rows = conn.execute(
        "SELECT card_created_at FROM sprint_metrics.board_events "
        "WHERE card_id = 'c_created' AND type = 'started' AND event_time = '2024-01-03T10:00:00Z'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == datetime(2024, 1, 1, 8, 30, 0, tzinfo=UTC)


def test_board_events_has_cost_columns(conn):
    """AC1: init_db creates the five cost columns with correct types."""
    rows = conn.execute(
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'sprint_metrics' AND table_name = 'board_events'
        AND column_name IN ('model_seconds', 'input_tokens', 'cached_input_tokens',
                            'output_tokens', 'reasoning_output_tokens')
        ORDER BY column_name
        """
    ).fetchall()
    column_map = {r[0]: r[1] for r in rows}
    assert len(column_map) == 5
    assert column_map["model_seconds"] == "integer"
    assert column_map["input_tokens"] == "bigint"
    assert column_map["cached_input_tokens"] == "bigint"
    assert column_map["output_tokens"] == "bigint"
    assert column_map["reasoning_output_tokens"] == "bigint"


def test_finished_row_stores_cost_values(conn):
    """AC2: a 'finished' row with cost fields stores all five values."""
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cost_fin', 'cost_start')"
    )
    conn.commit()
    insert_event(
        conn,
        {
            "card_id": "cost_fin",
            "type": "finished",
            "timestamp": "2024-01-10T15:00:00Z",
            "sprint": "2024-01",
            "card": {
                "created": "2024-01-01",
                "model_seconds": 3500,
                "input_tokens": 4000,
                "cached_input_tokens": 1400,
                "output_tokens": 900,
                "reasoning_output_tokens": 300,
            },
        },
    )
    rows = conn.execute(
        "SELECT model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens "
        "FROM sprint_metrics.board_events "
        "WHERE card_id = 'cost_fin' AND type = 'finished'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == (3500, 4000, 1400, 900, 300)


def test_non_finished_row_has_null_cost(conn):
    """AC2: rows for every other event type have all five cost columns NULL."""
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('cost_fin2', 'cost_start2')"
    )
    conn.commit()
    for event_type in (
        "started",
        "blocked",
        "unblocked",
        "escalated",
        "attempt_failed",
        "superseded",
    ):
        insert_event(
            conn,
            {
                "card_id": "cost_start2",
                "type": event_type,
                "timestamp": "2024-01-05T10:00:00Z",
                "sprint": "2024-01",
                "card": {"created": "2024-01-01"},
            },
        )
    rows = conn.execute(
        "SELECT model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens "
        "FROM sprint_metrics.board_events WHERE card_id = 'cost_start2'"
    ).fetchall()
    assert len(rows) == 6
    for row in rows:
        assert row == (None, None, None, None, None)


def test_resend_cost_fills_null(conn):
    """AC4: re-sending a 'finished' event with cost fills NULL cost columns."""
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost_fill'")
    conn.commit()
    insert_event(
        conn,
        {
            "card_id": "cost_fill",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01"},
        },
    )
    insert_event(
        conn,
        {
            "card_id": "cost_fill",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {
                "created": "2024-01-01",
                "model_seconds": 1200,
                "input_tokens": 5000,
                "cached_input_tokens": 2000,
                "output_tokens": 1000,
                "reasoning_output_tokens": 500,
            },
        },
    )
    rows = conn.execute(
        "SELECT model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens "
        "FROM sprint_metrics.board_events WHERE card_id = 'cost_fill' AND type = 'finished'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == (1200, 5000, 2000, 1000, 500)


def test_resend_cost_keeps_existing(conn):
    """AC4: re-sending a 'finished' event with different cost does not overwrite stored values."""
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost_keep'")
    conn.commit()
    insert_event(
        conn,
        {
            "card_id": "cost_keep",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {
                "created": "2024-01-01",
                "model_seconds": 3500,
                "input_tokens": 4000,
                "cached_input_tokens": 1400,
                "output_tokens": 900,
                "reasoning_output_tokens": 300,
            },
        },
    )
    insert_event(
        conn,
        {
            "card_id": "cost_keep",
            "type": "finished",
            "timestamp": "2024-01-07T15:00:00Z",
            "sprint": "2024-01",
            "card": {
                "created": "2024-01-01",
                "model_seconds": 9999,
                "input_tokens": 9999,
                "cached_input_tokens": 9999,
                "output_tokens": 9999,
                "reasoning_output_tokens": 9999,
            },
        },
    )
    rows = conn.execute(
        "SELECT model_seconds, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens "
        "FROM sprint_metrics.board_events WHERE card_id = 'cost_keep' AND type = 'finished'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == (3500, 4000, 1400, 900, 300)
