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


def test_reconstruct_card_carries_cost_from_finished_row():
    """AC3: a finished row's cost values are set on the reconstructed Card."""
    from datetime import date

    from sprint_metrics.store import query_sprint

    events = [
        (
            "started",
            datetime(2024, 1, 3, 10, 0),
            date(2024, 1, 2),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "finished",
            datetime(2024, 1, 10, 15, 0),
            date(2024, 1, 2),
            None,
            None,
            None,
            None,
            None,
            None,
            3500,
            4000,
            1400,
            900,
            300,
        ),
    ]
    conn = _FakeSprintConn(
        {
            "cost-a": {
                "sprints": {"2024-01"},
                "events": events,
            }
        }
    )
    cards = query_sprint(conn, "2024-01")
    assert len(cards) == 1
    card = cards[0]
    assert card.model_seconds == 3500
    assert card.input_tokens == 4000
    assert card.cached_input_tokens == 1400
    assert card.output_tokens == 900
    assert card.reasoning_output_tokens == 300


def test_reconstruct_card_without_cost_is_none():
    """AC3: a finished row with no cost values gives a card with all cost fields None."""
    from datetime import date

    from sprint_metrics.store import query_sprint

    events = [
        (
            "started",
            datetime(2024, 1, 3, 10, 0),
            date(2024, 1, 2),
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "finished",
            datetime(2024, 1, 10, 15, 0),
            date(2024, 1, 2),
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
            "no-cost": {
                "sprints": {"2024-01"},
                "events": events,
            }
        }
    )
    cards = query_sprint(conn, "2024-01")
    assert len(cards) == 1
    card = cards[0]
    assert card.model_seconds is None
    assert card.input_tokens is None
    assert card.cached_input_tokens is None
    assert card.output_tokens is None
    assert card.reasoning_output_tokens is None


def test_reconstruct_card_cost_values_exact():
    """AC6: model_seconds stays 3500, not converted to minutes."""
    from datetime import date

    from sprint_metrics.store import query_sprint

    events = [
        (
            "finished",
            datetime(2024, 1, 10, 15, 0),
            date(2024, 1, 2),
            None,
            None,
            None,
            None,
            None,
            None,
            3500,
            4000,
            1400,
            900,
            300,
        ),
    ]
    conn = _FakeSprintConn(
        {
            "cost-a": {
                "sprints": {"2024-01"},
                "events": events,
            }
        }
    )
    cards = query_sprint(conn, "2024-01")
    assert len(cards) == 1
    assert cards[0].model_seconds == 3500
    assert cards[0].input_tokens == 4000
    assert cards[0].cached_input_tokens == 1400
    assert cards[0].output_tokens == 900
    assert cards[0].reasoning_output_tokens == 300


def test_reconstruct_card_cost_per_card():
    """AC7: two stories in a sprint each carry their own cost values."""
    from datetime import date

    from sprint_metrics.store import query_sprint

    events_a = [
        (
            "finished",
            datetime(2024, 1, 10, 15, 0),
            date(2024, 1, 2),
            None,
            None,
            None,
            None,
            None,
            None,
            600,
            500,
            100,
            200,
            50,
        ),
    ]
    events_b = [
        (
            "finished",
            datetime(2024, 1, 10, 16, 0),
            date(2024, 1, 3),
            None,
            None,
            None,
            None,
            None,
            None,
            3000,
            9000,
            4000,
            5000,
            1000,
        ),
    ]
    conn = _FakeSprintConn(
        {
            "story-a": {
                "sprints": {"2024-01"},
                "events": events_a,
            },
            "story-b": {
                "sprints": {"2024-01"},
                "events": events_b,
            },
        }
    )
    cards = query_sprint(conn, "2024-01")
    assert len(cards) == 2
    card_a = next(c for c in cards if c.model_seconds == 600)
    card_b = next(c for c in cards if c.model_seconds == 3000)
    assert card_a.input_tokens == 500
    assert card_a.cached_input_tokens == 100
    assert card_a.output_tokens == 200
    assert card_a.reasoning_output_tokens == 50
    assert card_b.input_tokens == 9000
    assert card_b.cached_input_tokens == 4000
    assert card_b.output_tokens == 5000
    assert card_b.reasoning_output_tokens == 1000
