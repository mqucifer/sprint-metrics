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

from sprint_metrics.store import init_db, upsert_sprint

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
