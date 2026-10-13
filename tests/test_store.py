"""Tests for the store module against a live Postgres database.

Skips when SPRINT_METRICS_DB is not set.
"""

from __future__ import annotations

import os
from datetime import date

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
