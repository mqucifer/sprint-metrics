"""Tests that query_sprint handles superseded events, using a fake connection.

These tests run without a live Postgres database.
"""

from __future__ import annotations

from datetime import datetime


class _FakeSprintCursor:
    """In-memory cursor for the fake connection."""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSprintConn:
    """In-memory stand-in for a psycopg connection, sufficient for
    store.query_sprint. No database or SPRINT_METRICS_DB required.

    ``data`` maps card_id to a dict with:
      - ``sprints``: a set of sprint labels that have a finished or superseded row
      - ``events``: a list of 9-tuples matching the SELECT in query_sprint
    """

    def __init__(self, data):
        self._data = data

    def execute(self, sql, params=()):
        if "DISTINCT card_id" in sql:
            label = params[0]
            rows = [(card_id,) for card_id, info in self._data.items() if label in info["sprints"]]
        else:
            card_id = params[0]
            rows = self._data[card_id]["events"]
        return _FakeSprintCursor(rows)


def test_query_sprint_returns_superseded_card_with_because():
    """AC1: a card with a superseded row and no finished row is returned superseded."""
    from datetime import date

    from sprint_metrics.store import query_sprint

    events = [
        (
            "superseded",
            datetime(2024, 1, 4, 10, 0),
            date(2024, 1, 2),
            None,
            None,
            None,
            None,
            None,
            "sponsor",
        ),
    ]
    conn = _FakeSprintConn(
        {
            "sup19_c1": {
                "sprints": {"Sprint 19"},
                "events": events,
            }
        }
    )
    cards = query_sprint(conn, "Sprint 19")
    assert len(cards) == 1
    assert cards[0].superseded is True
    assert cards[0].superseded_because == "sponsor"


def test_query_sprint_superseded_points():
    """AC2: a superseded card's points flow through calculate_superseded_points."""
    from datetime import date

    from sprint_metrics.metrics import calculate_superseded_points
    from sprint_metrics.store import query_sprint

    events = [
        (
            "superseded",
            datetime(2024, 2, 4, 10, 0),
            date(2024, 2, 2),
            None,
            None,
            None,
            None,
            5,
            "story_problem",
        ),
    ]
    conn = _FakeSprintConn(
        {
            "sup20_c1": {
                "sprints": {"Sprint 20"},
                "events": events,
            }
        }
    )
    cards = query_sprint(conn, "Sprint 20")
    assert calculate_superseded_points(cards) == 5


def test_query_sprint_finished_card_not_superseded():
    """AC3: a started+finished card with no superseded row is not superseded."""
    from datetime import date

    from sprint_metrics.store import query_sprint

    events = [
        (
            "started",
            datetime(2024, 3, 3, 10, 0),
            date(2024, 3, 2),
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "finished",
            datetime(2024, 3, 5, 10, 0),
            date(2024, 3, 2),
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ]
    conn = _FakeSprintConn(
        {
            "s99_c1": {
                "sprints": {"Sprint 99"},
                "events": events,
            }
        }
    )
    cards = query_sprint(conn, "Sprint 99")
    assert len(cards) == 1
    assert cards[0].superseded is False
    assert cards[0].superseded_because is None
