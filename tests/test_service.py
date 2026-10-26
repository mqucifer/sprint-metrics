"""Tests for the stateful HTTP service in sprint_metrics.service."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, date

import pytest

from sprint_metrics.card import Card
from sprint_metrics.service import _compute_cost_summary, _median, _start_service, run
from sprint_metrics.store import init_db

SPRINT_METRICS_DB = os.environ.get("SPRINT_METRICS_DB")

requires_db = pytest.mark.skipif(SPRINT_METRICS_DB is None, reason="SPRINT_METRICS_DB not set")


class _InMemoryLogExporter:
    """Minimal in-memory log exporter for testing (opentelemetry-sdk lacks one)."""

    def __init__(self):
        self._logs = []

    def export(self, logs):
        self._logs.extend(logs)

    def flush(self):
        pass

    def shutdown(self):
        pass

    def get_finished_logs(self):
        return list(self._logs)


@pytest.fixture(autouse=True)
def _clean_board_events():
    """Ensure each test runs against a clean board_events and sprints table."""
    if SPRINT_METRICS_DB is None:
        return
    import psycopg

    conn = None
    try:
        conn = psycopg.connect(SPRINT_METRICS_DB, connect_timeout=5)
        conn.execute("DELETE FROM sprint_metrics.board_events")
        conn.execute("DELETE FROM sprint_metrics.sprints")
        conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()


def _make_event(
    card_id: str = "c1",
    event_type: str = "started",
    timestamp: str = "2024-01-03T10:00:00Z",
    sprint: str = "2024-01",
    created: str = "2024-01-01",
    **card_extra: object,
) -> dict:
    """Build a valid event dict for POST /events."""
    return {
        "api_version": "1",
        "card_id": card_id,
        "type": event_type,
        "timestamp": timestamp,
        "sprint": sprint,
        "card": {"created": created, **card_extra},
    }


def _post_events(url: str, event: dict) -> tuple[int, dict]:
    """POST an event and return (status, parsed_json_body)."""
    data = json.dumps(event).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _get_json(url: str) -> tuple[int, dict]:
    """GET a URL and return (status, parsed_json_body)."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


@requires_db
def test_get_sprint_returns_410_with_label():
    """AC1: GET /sprint?label=2024-01 returns 410 with error naming the removal
    and pointing to GET /range."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 410
        assert "error" in body
        assert "removed" in body["error"]
        assert "/range" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_returns_410_without_query_string():
    """AC2: GET /sprint with no query string returns 410 without a database query."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint")
        assert status == 410
        assert "error" in body
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_returns_410_when_db_unreachable():
    """AC2: GET /sprint?label=2024-01 with unreachable DB returns the same 410
    answer without a database query being attempted."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=2024-01")
        assert status == 410
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_no_query_string_returns_410_not_400():
    """AC2: GET /sprint (no label at all) is answered 410, distinct from the 400
    validation answer and the 503/500 conditions."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint")
        assert status == 410
        assert status not in (200, 400, 404, 500, 503)
        assert "error" in body
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
def test_get_sprint_empty_label_returns_410():
    """AC2: GET /sprint?label= (empty label) is answered 410 without a database
    query, the same as a missing label."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/sprint?label=")
        assert status == 410
        assert "removed" in body["error"]
    finally:
        pass


@requires_db
@pytest.mark.parametrize("path", ["/metrics", "/metrics?sprint=2024-01", "/metrics?"])
def test_get_metrics_returns_410_with_or_without_query_string(path):
    """#764 AC1: GET /metrics, with or without a query string, returns 410 with
    an error saying the endpoint has been removed, even with stored events."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        for event in (
            _make_event("c1", "started", "2024-01-03T10:00:00Z"),
            _make_event("c1", "finished", "2024-01-05T10:00:00Z"),
        ):
            assert _post_events(f"{base}/events", event)[0] == 200

        status, body = _get_json(f"{base}{path}")
        assert status == 410
        assert status not in (200, 400, 404, 500, 503)
        assert "endpoint removed" in body["error"]
        assert "/metrics" in body["error"]
    finally:
        conn.close()


@requires_db
def test_get_metrics_returns_410_when_db_unreachable():
    """#764 AC1: GET /metrics with the database unreachable is answered the same
    410, without a database query being attempted."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    status, body = _get_json(f"http://127.0.0.1:{port}/metrics")
    assert status == 410
    assert "endpoint removed" in body["error"]


def test_no_route_builds_prometheus_text_from_stored_events():
    """#764 AC5: the service no longer carries a Prometheus text formatter for
    stored events, and GET /metrics is gone from the endpoint list."""
    import sprint_metrics.service as service

    assert not hasattr(service, "_metrics_text")
    assert ("GET", "/metrics") not in [(m, p) for m, p, _ in service.SERVICE_ENDPOINTS]


def _cost_card(
    card_id: str,
    model_seconds: int,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_output_tokens: int,
) -> Card:
    """A finished card carrying a full cost payload."""
    return Card(
        created=date(2024, 1, 1),
        model_seconds=model_seconds,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        card_id=card_id,
    )


def test_compute_cost_summary_single_story_six_keys_and_rounded_minutes():
    """AC1: one costed story's item has exactly the six keys, card_id, and
    model_minutes is model_seconds expressed in whole minutes (rounded)."""
    card = _cost_card("cost-a", 3500, 4000, 1400, 900, 300)
    story_costs, cost = _compute_cost_summary([card])
    assert len(story_costs) == 1
    item = story_costs[0]
    assert set(item.keys()) == {
        "card_id",
        "model_minutes",
        "input_tokens",
        "cached_input_percent",
        "output_tokens",
        "reasoning_output_percent",
    }
    assert item["card_id"] == "cost-a"
    assert item["model_minutes"] == 58
    assert item["input_tokens"] == 4000
    assert item["output_tokens"] == 900
    assert cost["total"]["model_minutes"] == 58


def test_compute_cost_summary_percents_are_the_sprints_not_the_stories():
    """AC2: every item carries the sprint's combined cached/reasoning shares, not
    each story's own share (story A's own 50% / story B's 30% are both reported
    as the sprint's 35% / 26%)."""
    a = _cost_card("a", 60, 1000, 500, 800, 400)
    b = _cost_card("b", 60, 3000, 900, 3200, 640)
    story_costs, _ = _compute_cost_summary([a, b])
    for item in story_costs:
        assert item["cached_input_percent"] == 35
        assert item["reasoning_output_percent"] == 26


def test_compute_cost_summary_middle_is_median_and_total_is_sum():
    """AC3: cost.middle is the median and cost.total is the sum of the per-story
    values for each measure."""
    c1 = _cost_card("c1", 120, 300, 0, 100, 0)
    c2 = _cost_card("c2", 300, 900, 0, 200, 0)
    c3 = _cost_card("c3", 540, 600, 0, 400, 0)
    _, cost = _compute_cost_summary([c1, c2, c3])
    assert cost["middle"]["model_minutes"] == 5
    assert cost["total"]["model_minutes"] == 16
    assert cost["middle"]["input_tokens"] == 600
    assert cost["total"]["input_tokens"] == 1800
    assert cost["middle"]["output_tokens"] == 200
    assert cost["total"]["output_tokens"] == 700


def test_compute_cost_summary_cost_object_holds_only_the_three_measures():
    """AC9: cost.middle and cost.total each carry exactly model_minutes,
    input_tokens and output_tokens; the two percents ride only on story_costs
    items and never appear inside cost."""
    c1 = _cost_card("c1", 120, 300, 0, 100, 0)
    c2 = _cost_card("c2", 300, 900, 0, 200, 0)
    c3 = _cost_card("c3", 540, 600, 0, 400, 0)
    _, cost = _compute_cost_summary([c1, c2, c3])
    measure_keys = {"model_minutes", "input_tokens", "output_tokens"}
    assert set(cost["middle"].keys()) == measure_keys
    assert set(cost["total"].keys()) == measure_keys
    assert "cached_input_percent" not in cost
    assert "reasoning_output_percent" not in cost
    assert cost["middle"] == {"model_minutes": 5, "input_tokens": 600, "output_tokens": 200}
    assert cost["total"] == {"model_minutes": 16, "input_tokens": 1800, "output_tokens": 700}


def test_compute_cost_summary_excludes_stories_without_cost():
    """AC4: a finished story carrying no cost data is omitted from story_costs,
    and the middle/total are computed from the costed stories only."""
    costed = _cost_card("c1", 120, 300, 0, 100, 0)
    bare = Card(created=date(2024, 1, 1), card_id="bare")
    story_costs, cost = _compute_cost_summary([costed, bare])
    assert [item["card_id"] for item in story_costs] == ["c1"]
    assert cost["middle"]["model_minutes"] == 2
    assert cost["total"]["model_minutes"] == 2


def test_compute_cost_summary_empty_when_no_story_carries_cost():
    """AC5: when no story carries cost data (or there are no cards), story_costs
    is an empty list and cost is None."""
    bare1 = Card(created=date(2024, 1, 1), card_id="b1")
    bare2 = Card(created=date(2024, 1, 1), card_id="b2")
    assert _compute_cost_summary([bare1, bare2]) == ([], None)
    assert _compute_cost_summary([]) == ([], None)


def test_compute_cost_summary_short_story_rounds_to_whole_minutes():
    """AC10: model_seconds 119 -> model_minutes 2 (119/60 ≈ 1.98 rounded, not
    truncated to 1), so a short story never reads as a free story."""
    card = _cost_card("short", 119, 100, 0, 10, 0)
    story_costs, _ = _compute_cost_summary([card])
    assert story_costs[0]["model_minutes"] == 2


def test_median_odd_even_and_single():
    """The middle value: median for odd counts, the rounded average of the two
    middle values for even counts, the lone value for a single element."""
    assert _median([2, 5, 9]) == 5
    assert _median([58, 59]) == 58
    assert _median([4]) == 4
    assert _median([1, 2, 3, 4]) == round((2 + 3) / 2)


def _stub_range_result(labels):
    """Mimic format_sprint_range_json's per-sprint entries: prior/delta dicts after the first."""
    result = {"sprints": {}}
    for i, label in enumerate(labels):
        entry = {"cycle_time_days": 0, "throughput": 0, "flags": {}}
        if i == 0:
            entry["prior"] = None
            entry["delta"] = None
        else:
            entry["prior"] = {"cycle_time_days": 0}
            entry["delta"] = {"cycle_time_days": 0}
        result["sprints"][label] = entry
    return result


def test_attach_range_cost_entry_carries_cost_and_prior_delta():
    """AC1/AC9: each range entry carries story_costs and cost matching /sprint, and the
    second entry's prior and delta carry the six flat cost names (current minus prior)."""
    from sprint_metrics.service import _attach_range_cost, _compute_cost_summary, _cost_flat

    prior_cards = [
        _cost_card("p1", 1080, 2500, 1000, 600, 100),
        _cost_card("p2", 1860, 4000, 1600, 1200, 200),
        _cost_card("p3", 2580, 8000, 3200, 3800, 400),
    ]
    current_cards = [
        _cost_card("c1", 3480, 4000, 1800, 900, 200),
        _cost_card("c2", 5400, 12000, 5840, 4800, 1200),
    ]
    sprints = {"2026-09": prior_cards, "2026-10": current_cards}
    labels = ["2026-09", "2026-10"]
    has_events = {"2026-09", "2026-10"}
    result = _stub_range_result(labels)
    _attach_range_cost(result, sprints, labels, has_events)

    e09 = result["sprints"]["2026-09"]
    assert e09["prior"] is None
    assert e09["delta"] is None
    sc09, cost09 = _compute_cost_summary(prior_cards)
    assert e09["story_costs"] == sc09
    assert e09["cost"] == cost09
    assert e09["cost"]["middle"]["model_minutes"] == 31
    assert e09["cost"]["total"]["model_minutes"] == 92
    assert e09["cost"]["middle"]["input_tokens"] == 4000
    assert e09["cost"]["total"]["input_tokens"] == 14500
    assert e09["cost"]["middle"]["output_tokens"] == 1200
    assert e09["cost"]["total"]["output_tokens"] == 5600

    e10 = result["sprints"]["2026-10"]
    sc10, cost10 = _compute_cost_summary(current_cards)
    assert e10["story_costs"] == sc10
    assert e10["cost"] == cost10
    prior_flat = _cost_flat(cost09)
    cur_flat = _cost_flat(cost10)
    for name in prior_flat:
        assert e10["prior"][name] == prior_flat[name]
        assert e10["delta"][name] == (
            cur_flat[name] - prior_flat[name]
            if cur_flat[name] is not None and prior_flat[name] is not None
            else None
        )
    assert e10["prior"]["model_minutes_middle"] == 31
    assert e10["prior"]["model_minutes_total"] == 92
    assert e10["prior"]["input_tokens_middle"] == 4000
    assert e10["prior"]["input_tokens_total"] == 14500
    assert e10["prior"]["output_tokens_middle"] == 1200
    assert e10["prior"]["output_tokens_total"] == 5600


def test_attach_range_cost_prior_no_costed_stories_nulls_cost():
    """AC2: the preceding sprint has events but no costed stories, so its non-null prior
    object carries null for the six cost values and the delta carries null for each."""
    from sprint_metrics.service import _attach_range_cost

    prior_cards = [Card(created=date(2024, 1, 1), card_id="p")]
    current_cards = [
        _cost_card("c1", 3480, 4000, 1800, 900, 200),
        _cost_card("c2", 5400, 12000, 5840, 4800, 1200),
    ]
    sprints = {"2024-01": prior_cards, "2024-02": current_cards}
    labels = ["2024-01", "2024-02"]
    has_events = {"2024-01", "2024-02"}
    result = _stub_range_result(labels)
    _attach_range_cost(result, sprints, labels, has_events)

    e02 = result["sprints"]["2024-02"]
    assert e02["prior"] is not None
    assert e02["delta"] is not None
    for name in (
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
    ):
        assert e02["prior"][name] is None
        assert e02["delta"][name] is None


def test_attach_range_cost_null_entry_for_no_events():
    """AC3: a range entry for a sprint with no events is the all-null entry, with
    story_costs an empty array and cost null, alongside the entry's other null metrics."""
    from sprint_metrics.service import _attach_range_cost

    current_cards = [_cost_card("c1", 3480, 4000, 1800, 900, 200)]
    sprints = {"2024-01": [], "2024-02": current_cards}
    labels = ["2024-01", "2024-02"]
    has_events = {"2024-02"}
    result = _stub_range_result(labels)
    _attach_range_cost(result, sprints, labels, has_events)

    e01 = result["sprints"]["2024-01"]
    assert e01["story_costs"] == []
    assert e01["cost"] is None
    assert e01["prior"] is None
    assert e01["delta"] is None
    e02 = result["sprints"]["2024-02"]
    assert e02["prior"] is None
    assert e02["delta"] is None


@requires_db
def test_post_valid_event_returns_200_no_error():
    """AC1: POST /events with a valid started event returns 200 and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_test'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_test")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_duplicate_finished_event_idempotent():
    """AC2: POSTing the same finished event twice results in throughput=1, not 2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_test'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_test",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        finished = _make_event(
            card_id="ac2_test",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)
        # Post the identical finished event again
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", finished)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_returns_400():
    """AC3: POST /events with type 'invalid_type' returns 400 with error naming the type."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="invalid_type")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "invalid_type" in body["error"]
    finally:
        conn.close()


def test_service_exits_nonzero_on_unreachable_db(capsys):
    """AC4: SPRINT_METRICS_DB pointing to unreachable Postgres: non-zero exit,
    stderr references the database connection."""
    exit_code = run("postgresql://user:pass@127.0.0.1:19999/nonexistent")
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "database" in captured.err.lower() or "connection" in captured.err.lower()


@requires_db
def test_post_response_content_type_and_no_error():
    """AC5: POST valid event → Content-Type is application/json, body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_test'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac5_test")
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_frobnicated_error_contains_type():
    """AC6: POST with type 'frobnicated' → error string contains 'frobnicated'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "frobnicated" in body["error"]
    finally:
        conn.close()


@requires_db
def test_range_response_metrics_and_keys():
    """AC1: GET /range?start=2024-01&end=2024-02 returns 200, api_version '1',
    sprints has keys '2024-01' and '2024-02' with correct throughput and cycle_time_days."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_range', 'ac2_range')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: card created 2024-01-01, started 2024-01-03, finished 2024-01-07
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: card created 2024-02-01, started 2024-02-03, finished 2024-02-06
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["api_version"] == "4"
        assert set(body["sprints"].keys()) == {"2024-01", "2024-02"}
        assert body["sprints"]["2024-01"]["throughput"] == 1
        assert body["sprints"]["2024-01"]["cycle_time_days"] == 4
        assert body["sprints"]["2024-02"]["throughput"] == 1
        assert body["sprints"]["2024-02"]["cycle_time_days"] == 3
    finally:
        conn.close()


@requires_db
def test_range_prior_and_delta():
    """AC2: 2024-01 has prior=null and delta=null; 2024-02 has prior.throughput=1
    and delta.throughput=0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac2_range_a', 'ac2_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["sprints"]["2024-01"]["prior"] is None
        assert body["sprints"]["2024-01"]["delta"] is None
        assert body["sprints"]["2024-02"]["prior"]["throughput"] == 1
        assert body["sprints"]["2024-02"]["delta"]["throughput"] == 0
    finally:
        conn.close()


@requires_db
def test_range_start_after_end_returns_400():
    """AC3: GET /range?start=2024-02&end=2024-01 returns 400 with error referencing
    the invalid range."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-02&end=2024-01")
        assert status == 400
        assert "error" in body
        assert "range" in body["error"] or "2024-02" in body["error"]
    finally:
        conn.close()


@requires_db
def test_range_sprints_in_chronological_order():
    """AC4: the sprints object has exactly two keys and '2024-01' appears before
    '2024-02' in the serialized JSON (chronological order)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac4_range_a', 'ac4_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02", timeout=5
        ) as resp:
            raw_body = resp.read().decode()

        body = json.loads(raw_body)
        assert len(body["sprints"]) == 2
        assert list(body["sprints"].keys()) == ["2024-01", "2024-02"]
        # Verify in the raw serialized JSON: "2024-01" appears before "2024-02"
        idx_01 = raw_body.index('"2024-01"')
        idx_02 = raw_body.index('"2024-02"')
        assert idx_01 < idx_02
    finally:
        conn.close()


@requires_db
def test_range_first_sprint_prior_and_delta_are_null():
    """AC5: the '2024-01' entry has prior with a JSON null value and delta with a
    JSON null value, because 2024-01 is the first sprint in the range."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac5_range_a', 'ac5_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02", timeout=5
        ) as resp:
            raw_body = resp.read().decode()

        body = json.loads(raw_body)
        # prior must be JSON null (not the string 'null', not an empty object)
        assert body["sprints"]["2024-01"]["prior"] is None
        assert body["sprints"]["2024-01"]["delta"] is None
        # Verify the raw JSON contains 'null' not '"null"' or '{}'
        assert '"prior": null' in raw_body or '"prior":null' in raw_body
    finally:
        conn.close()


@requires_db
def test_range_second_sprint_prior_and_delta_values():
    """AC6: the '2024-02' entry's prior object has throughput=1 and
    cycle_time_days=4, and its delta object has throughput=0 and cycle_time_days=-1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_range_a', 'ac6_range_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: throughput 1, cycle_time 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: throughput 1, cycle_time 3
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        assert body["sprints"]["2024-02"]["prior"]["throughput"] == 1
        assert body["sprints"]["2024-02"]["prior"]["cycle_time_days"] == 4
        assert body["sprints"]["2024-02"]["delta"]["throughput"] == 0
        assert body["sprints"]["2024-02"]["delta"]["cycle_time_days"] == -1
    finally:
        conn.close()


@requires_db
def test_schema_event_get_returns_200_json_schema():
    """AC1: GET /schema/event returns 200, Content-Type application/json, body is a
    JSON Schema whose $schema is draft 2020-12 and required includes api_version."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/schema/event", timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "api_version" in body["required"]
    finally:
        conn.close()


@requires_db
def test_schema_event_card_and_type_constraints():
    """AC2: schema's properties include a card object whose required includes 'created',
    and the schema constrains type to the eight accepted values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card = body["properties"]["card"]
        assert "created" in card["required"]
        type_enum = body["properties"]["type"]["enum"]
        assert set(type_enum) == {
            "started",
            "blocked",
            "unblocked",
            "finished",
            "escalated",
            "attempt_failed",
            "superseded",
            "returned",
        }
    finally:
        conn.close()


@requires_db
def test_schema_event_post_returns_405():
    """AC3: POST to /schema/event returns 405."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        data = b"{}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/schema/event",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 405
    finally:
        conn.close()


@requires_db
def test_schema_event_top_level_structure():
    """UX4: top-level $schema, type=object, required includes api_version, card_id,
    type, timestamp, sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert body["type"] == "object"
        for field in ("api_version", "card_id", "type", "timestamp", "sprint"):
            assert field in body["required"]
    finally:
        conn.close()


@requires_db
def test_schema_event_type_enum_exact():
    """AC3+UX4: properties.type.enum is an array of exactly eight strings in order:
    started, blocked, unblocked, finished, escalated, attempt_failed, superseded,
    returned."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        assert body["properties"]["type"]["enum"] == [
            "started",
            "blocked",
            "unblocked",
            "finished",
            "escalated",
            "attempt_failed",
            "superseded",
            "returned",
        ]
    finally:
        conn.close()


@requires_db
def test_schema_event_card_created_properties():
    """UX6: properties.card has type=object, required includes 'created',
    and properties.card.properties.created has type=string and format=date."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card = body["properties"]["card"]
        assert card["type"] == "object"
        assert "created" in card["required"]
        created = card["properties"]["created"]
        assert created["type"] == "string"
        assert created["format"] == "date"
    finally:
        conn.close()


@requires_db
def test_health_returns_200_when_db_reachable():
    """AC1: GET /health returns 200 when SPRINT_METRICS_DB is reachable."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/health")
        assert status == 200
    finally:
        conn.close()


@requires_db
def test_health_returns_200_with_nonempty_body():
    """AC2: GET /health returns 200 and body has at least one byte when no events stored."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read()
        assert len(body) >= 1
    finally:
        conn.close()


@requires_db
def test_health_body_is_json_object_not_empty():
    """AC3: GET /health body is parseable as JSON and length > 2 (not '{}')."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            body = resp.read().decode()
        parsed = json.loads(body)
        assert isinstance(parsed, dict)
        assert len(body) > 2
    finally:
        conn.close()


@requires_db
def test_health_returns_non_200_when_db_unreachable():
    """AC4: GET /health returns non-200 when the Postgres connection is dead."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    # Close the connection to simulate the DB being killed
    conn.close()

    status, body = _get_json(f"http://127.0.0.1:{port}/health")
    assert status != 200


@requires_db
def test_service_works_without_otel_endpoint(monkeypatch, capsys):
    """AC3: endpoint not set → service responds 200, no error key, no ConnectionError on stderr."""
    import psycopg

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    init_telemetry()

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_telemetry'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac3_telemetry")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        captured = capsys.readouterr()
        assert "ConnectionError" not in captured.err
        assert "connection refused" not in captured.err
    finally:
        conn.close()


@requires_db
def test_post_events_span_name_and_attributes(monkeypatch):
    """AC1: POST /events → exactly one span named 'POST /events' with http.method and http.route."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_span'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_span")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        spans = exporter.get_finished_spans()
        matching = [s for s in spans if "POST" in s.name and "/events" in s.name]
        assert len(matching) == 1
        span = matching[0]
        assert span.attributes["http.method"] == "POST"
        assert span.attributes["http.route"] == "/events"
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_span_error_status(monkeypatch):
    """AC3: POST /events with invalid type 'frobnicated' → span status is not OK."""
    import psycopg
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    exporter = InMemorySpanExporter()
    init_telemetry(span_exporter=exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400

        spans = exporter.get_finished_spans()
        matching = [s for s in spans if "POST" in s.name and "/events" in s.name]
        assert len(matching) == 1
        span = matching[0]
        assert span.status.status_code != StatusCode.OK
    finally:
        conn.close()


@requires_db
def test_post_valid_event_emits_info_log_record(monkeypatch):
    """AC1: valid POST /events → in-memory log exporter has a record with severity INFO,
    body includes card_id and event type."""
    import psycopg
    from opentelemetry._logs import SeverityNumber

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    log_exporter = _InMemoryLogExporter()
    init_telemetry(log_exporter=log_exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="c1", event_type="started")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        logs = log_exporter.get_finished_logs()
        matching = [
            ld
            for ld in logs
            if "c1" in (ld.log_record.body or "") and "started" in (ld.log_record.body or "")
        ]
        assert len(matching) >= 1
        assert matching[0].log_record.severity_number == SeverityNumber.INFO
    finally:
        conn.close()


@requires_db
def test_post_invalid_type_emits_error_log_record(monkeypatch):
    """AC2: invalid type POST /events → in-memory log exporter has a record with severity ERROR,
    body includes the invalid type value."""
    import psycopg
    from opentelemetry._logs import SeverityNumber

    from sprint_metrics.telemetry import init_telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    log_exporter = _InMemoryLogExporter()
    init_telemetry(log_exporter=log_exporter)

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(event_type="frobnicated")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400

        logs = log_exporter.get_finished_logs()
        matching = [ld for ld in logs if "frobnicated" in (ld.log_record.body or "")]
        assert len(matching) >= 1
        assert matching[0].log_record.severity_number.value >= SeverityNumber.ERROR.value
    finally:
        conn.close()


@requires_db
def test_trend_cycle_time_three_sprints():
    """AC1: GET /trend?metric=cycle_time_days&start=2024-02&end=2024-04 returns
    200 with three entries: 2024-02 value 3, 2024-03 value null, 2024-04 value 6."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_trend_a', 'ac1_trend_b', 'ac1_trend_c', 'ac1_trend_d')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card, cycle 4 (created 01-01, started 01-02, finished 01-06)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: two cards, each cycle 3 (created 02-01, started 02-02, finished 02-05)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_b",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_c",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_c",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        # 2024-04: one card, cycle 6 (created 04-01, started 04-02, finished 04-08)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_d",
                event_type="started",
                timestamp="2024-04-02T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_d",
                event_type="finished",
                timestamp="2024-04-08T15:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-02&end=2024-04",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "4"
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-02", "value": 3}
        assert body["values"][1] == {"sprint": "2024-03", "value": None}
        assert body["values"][2] == {"sprint": "2024-04", "value": 6}
    finally:
        conn.close()


@requires_db
def test_trend_empty_db_all_zeros():
    """AC2: GET /trend?metric=throughput&start=2024-01&end=2024-03 on an empty DB
    returns 200 with three entries, all value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-03"
        )
        assert status == 200
        assert body["api_version"] == "4"
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert body["values"][2] == {"sprint": "2024-03", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_invalid_metric_returns_400():
    """AC2: GET /trend?metric=bogus_metric&start=2024-01&end=2024-02 returns 400
    with error containing 'bogus_metric'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=bogus_metric&start=2024-01&end=2024-02"
        )
        assert status == 400
        assert "bogus_metric" in body["error"]
    finally:
        conn.close()


@requires_db
def test_trend_start_after_end_returns_400():
    """AC4: GET /trend?metric=throughput&start=2024-03&end=2024-01 returns 400
    with error naming both '2024-03' and '2024-01'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-03&end=2024-01"
        )
        assert status == 400
        assert "2024-03" in body["error"]
        assert "2024-01" in body["error"]
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_rate_two_sprints():
    """AC5: GET /trend?metric=first_attempt_rate_percent&start=2024-01&end=2024-02
    returns 200 with two entries: 2024-01 value 100 (one card, attempts=1),
    2024-02 value 0 (one card, attempts=2)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac5_trend_a', 'ac5_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one completed card, default attempts=1 → 100%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # 2024-02: one completed card, attempts=2 → 0%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_trend_b",
                event_type="finished",
                timestamp="2024-02-07T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                attempts=2,
                failure_class="parse",
                failure_role="Developer",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_rate_percent"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["api_version"] == "4"
        assert len(body["values"]) == 2
        assert body["values"][0]["sprint"] == "2024-01"
        assert body["values"][0]["value"] == 100
        assert body["values"][1]["sprint"] == "2024-02"
        assert body["values"][1]["value"] == 0
    finally:
        conn.close()


@requires_db
def test_trend_response_includes_metric_and_span_labels():
    """UX6: GET /trend?metric=cycle_time_days&start=2024-01&end=2024-02 response
    has top-level keys whose values are 'cycle_time_days', '2024-01', '2024-02'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_trend_a', 'ac6_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_b",
                event_type="started",
                timestamp="2024-02-01T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac6_trend_b",
                event_type="finished",
                timestamp="2024-02-04T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-01&end=2024-02"
        )
        assert status == 200
        values = list(body.values())
        assert "cycle_time_days" in values
        assert "2024-01" in values
        assert "2024-02" in values
    finally:
        conn.close()


@requires_db
def test_trend_six_sprints_zero_fill_empty_sprint():
    """UX7: GET /trend?metric=throughput&start=2024-01&end=2024-06 with no events
    for 2024-03 returns six entries in order, 2024-03 has value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac7_trend_a', 'ac7_trend_b', 'ac7_trend_c', 'ac7_trend_d', 'ac7_trend_e')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Add one finished card to each of 2024-01, 02, 04, 05, 06 (not 03)
        sprints_with_data = ["2024-01", "2024-02", "2024-04", "2024-05", "2024-06"]
        for i, sprint in enumerate(sprints_with_data):
            card_id = f"ac7_trend_{chr(ord('a') + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp=f"{sprint}-03T10:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp=f"{sprint}-07T15:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-06"
        )
        assert status == 200
        assert len(body["values"]) == 6
        expected_order = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
        for entry, label in zip(body["values"], expected_order, strict=True):
            assert entry["sprint"] == label
        assert body["values"][2]["value"] is None
        assert body["values"][0]["value"] == 1
        assert body["values"][1]["value"] == 1
        assert body["values"][3]["value"] == 1
        assert body["values"][4]["value"] == 1
        assert body["values"][5]["value"] == 1
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_rate_integer_not_string_or_float():
    """UX8: GET /trend?metric=first_attempt_rate_percent with 2024-01 attempts=2
    (value 0) and 2024-02 attempts=1 (value 100) returns JSON integers."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac8_trend_a', 'ac8_trend_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-01: one card with attempts=2 → 0%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=2,
                failure_class="parse",
                failure_role="Developer",
            ),
        )
        # 2024-02: one card with attempts=1 (default) → 100%
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac8_trend_b",
                event_type="finished",
                timestamp="2024-02-07T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_rate_percent"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["values"][0]["sprint"] == "2024-01"
        assert body["values"][0]["value"] == 0
        assert isinstance(body["values"][0]["value"], int)
        assert not isinstance(body["values"][0]["value"], bool)
        assert body["values"][1]["sprint"] == "2024-02"
        assert body["values"][1]["value"] == 100
        assert isinstance(body["values"][1]["value"], int)
        assert not isinstance(body["values"][1]["value"], bool)
    finally:
        conn.close()


@requires_db
def test_schema_trend_get_returns_200_json_schema():
    """AC3: GET /schema/trend returns 200, application/json, correct $schema and required."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/schema/trend", timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "api_version" in body["required"]
    finally:
        conn.close()


@requires_db
def test_trend_response_validates_against_schema():
    """AC4 (UX): a /trend response validates against TREND_SCHEMA with no errors."""
    import jsonschema
    import psycopg

    from sprint_metrics.schema import TREND_SCHEMA

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_schema_a', 'ac4_schema_b', 'ac4_schema_c')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Three sprints with one finished card each (throughput = 1 each)
        for sprint, card_id in [
            ("2024-01", "ac4_schema_a"),
            ("2024-02", "ac4_schema_b"),
            ("2024-03", "ac4_schema_c"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp=f"{sprint}-03T10:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp=f"{sprint}-07T15:00:00Z",
                    sprint=sprint,
                    created=f"{sprint}-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-03"
        )
        assert status == 200
        jsonschema.validate(instance=body, schema=TREND_SCHEMA)
    finally:
        conn.close()


@requires_db
def test_post_events_returns_503_when_db_unreachable():
    """AC1+AC2: POST /events with unreachable DB returns 503 (not 500),
    body is non-empty and does not contain 'Traceback'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac1_503")
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                raw_body = resp.read().decode()
        except urllib.error.HTTPError as e:
            status = e.code
            raw_body = e.read().decode()
        assert status == 503
        assert status != 500
        assert len(raw_body) > 0
        assert "Traceback" not in raw_body
    finally:
        pass


@requires_db
def test_post_events_recover_after_connection_lost():
    """AC4: after the connection is lost, POST /events succeeds once the database
    is reachable again; subsequent GET /range returns throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()
    conn.close()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        started = _make_event(
            card_id="ac4_recover",
            event_type="started",
            timestamp="2024-01-05T09:00:00Z",
            sprint="2024-01",
            created="2024-01-04",
        )
        finished = _make_event(
            card_id="ac4_recover",
            event_type="finished",
            timestamp="2024-01-08T15:00:00Z",
            sprint="2024-01",
            created="2024-01-04",
        )
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", started)
        assert status == 200
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", finished)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["throughput"] == 1
    finally:
        pass


@requires_db
def test_post_events_503_content_type_is_application_json():
    """AC5: 503 response Content-Type header is exactly 'application/json'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac5_503")
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
        assert content_type == "application/json"
    finally:
        pass


@requires_db
def test_post_events_503_body_json_contains_database():
    """AC6: 503 body parsed as JSON is a dict, and at least one value (lowercased)
    contains the substring 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac6_503")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 503
        assert isinstance(body, dict)
        values_lowered = [str(v).lower() for v in body.values()]
        assert any("database" in v for v in values_lowered)
    finally:
        pass


@requires_db
def test_post_events_503_body_has_no_card_id_key():
    """AC7: 503 body parsed as JSON has no top-level key named 'card_id'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        event = _make_event(card_id="ac7_503")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 503
        assert "card_id" not in body
    finally:
        pass


@requires_db
def test_get_range_returns_503_when_db_unreachable():
    """AC2: GET /range?start=2024-01&end=2024-02 with unreachable DB returns 503 and non-empty body."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 503
        assert len(body) > 0
    finally:
        pass


@requires_db
def test_get_trend_returns_503_when_db_unreachable():
    """AC3: GET /trend?metric=throughput&start=2024-01&end=2024-02 with unreachable DB
    returns 503 and non-empty body."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-02"
        )
        assert status == 503
        assert len(body) > 0
    finally:
        pass


@requires_db
def test_get_range_invalid_range_400_no_database_in_error():
    """AC7 (UX): GET /range?start=2024-02&end=2024-01 with unreachable DB returns 400,
    Content-Type 'application/json', error contains 'invalid range' but not 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/range?start=2024-02&end=2024-01", timeout=5
            ) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
            body = json.loads(e.read().decode())
        assert content_type == "application/json"
        assert "error" in body
        assert "invalid range" in body["error"]
        assert "database" not in body["error"]
    finally:
        pass


@requires_db
def test_get_trend_503_content_type_and_database_in_body():
    """AC8 (UX): GET /trend?metric=throughput&start=2024-01&end=2024-02 with unreachable
    DB returns Content-Type 'application/json' and body has at least one value
    containing 'database'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/trend?metric=throughput&start=2024-01&end=2024-02",
                timeout=5,
            ) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            content_type = e.headers.get("Content-Type", "")
            body = json.loads(e.read().decode())
        assert content_type == "application/json"
        assert isinstance(body, dict)
        values_lowered = [str(v).lower() for v in body.values()]
        assert any("database" in v for v in values_lowered)
    finally:
        pass


@requires_db
def test_health_reconnects_after_connection_lost():
    """AC1: after the connection is lost and the DB is reachable again,
    GET /health returns 200 (the service reconnected automatically)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/health")
        assert status == 200
    finally:
        pass


@requires_db
def test_events_reconnects_after_connection_lost():
    """AC3: after the connection is lost, POST /events with a valid board event
    returns 200 and the body does not contain a key named 'error'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_reconnect'")
    conn.commit()

    port = _start_service(conn, 0, SPRINT_METRICS_DB)
    try:
        # Verify the service works with a live connection
        event = _make_event(
            card_id="ac3_reconnect",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        status, _ = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        # Simulate DB restart: close the connection
        conn.close()

        # POST a new event — the service should reconnect
        event2 = _make_event(
            card_id="c2",
            event_type="started",
            timestamp="2024-01-04T10:00:00Z",
            sprint="2024-01",
            created="2024-01-02",
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event2)
        assert status == 200
        assert "error" not in body
    finally:
        pass


@requires_db
def test_health_returns_503_when_db_stopped():
    """AC4: GET /health returns 503 when the database is unreachable and cannot be reconnected."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.close()

    # Use an unreachable URL to simulate the DB being stopped (not yet restarted)
    unreachable_url = "postgresql://user:pass@127.0.0.1:19999/nonexistent"
    port = _start_service(conn, 0, unreachable_url)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/health")
        assert status == 503
    finally:
        pass


@requires_db
def test_post_sprints_valid_returns_200_no_error():
    """AC1: POST /sprints with valid body returns 200, Content-Type application/json, no error key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'ac1_sprints'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        body = {
            "name": "ac1_sprints",
            "start_date": "2024-01-15",
            "end_date": "2024-02-15",
            "timezone": "UTC",
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            parsed = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert "error" not in parsed
    finally:
        conn.close()


@requires_db
def test_post_sprints_missing_name_returns_400():
    """AC2: POST /sprints without 'name' returns 400 with error containing 'name'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        body = {"start_date": "2024-01-15", "end_date": "2024-02-15", "timezone": "UTC"}
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                parsed = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            status = e.code
            parsed = json.loads(e.read().decode())
        assert status == 400
        assert "error" in parsed
        assert "name" in parsed["error"]
    finally:
        conn.close()


@requires_db
def test_post_sprints_invalid_date_returns_400():
    """AC3: POST /sprints with start_date '2024-13-45' returns 400 with error containing '2024-13-45'."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        body = {
            "name": "Sprint 18",
            "start_date": "2024-13-45",
            "end_date": "2024-02-15",
            "timezone": "UTC",
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                parsed = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            status = e.code
            parsed = json.loads(e.read().decode())
        assert status == 400
        assert "error" in parsed
        assert "2024-13-45" in parsed["error"]
    finally:
        conn.close()


@requires_db
def test_post_sprints_response_contains_name():
    """UX AC4: POST /sprints on empty sprints table returns 200, Content-Type application/json,
    body has 'name' key with the sprint name, no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        body = {
            "name": "Sprint 18",
            "start_date": "2026-10-07",
            "end_date": "2026-10-07",
            "timezone": "America/Chicago",
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            parsed = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert parsed["name"] == "Sprint 18"
        assert "error" not in parsed
    finally:
        conn.close()


@requires_db
def test_post_sprints_upsert_replaces_existing_row():
    """UX AC5: POST /sprints with existing name updates in place; DB has one row with new start_date."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # First registration
        body1 = {
            "name": "Sprint 18",
            "start_date": "2026-10-07",
            "end_date": "2026-10-07",
            "timezone": "America/Chicago",
        }
        data1 = json.dumps(body1).encode()
        req1 = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data1,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req1, timeout=5) as resp:
            assert resp.status == 200
            resp.read()

        # Upsert with new start_date
        body2 = {
            "name": "Sprint 18",
            "start_date": "2026-10-08",
            "end_date": "2026-10-08",
            "timezone": "UTC",
        }
        data2 = json.dumps(body2).encode()
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{port}/sprints",
            data=data2,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req2, timeout=5) as resp:
            status = resp.status
            resp.read()
        assert status == 200

        # Verify exactly one row with the updated start_date
        rows = conn.execute(
            "SELECT start_date FROM sprint_metrics.sprints WHERE name = %s",
            ("Sprint 18",),
        ).fetchall()
        assert len(rows) == 1
        assert str(rows[0][0]) == "2026-10-08"
    finally:
        conn.close()


@requires_db
def test_post_events_free_form_sprint_name_returns_200():
    """AC1: POST /events with sprint='Sprint 18' returns 200 and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_sprint_name'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac1_sprint_name", sprint="Sprint 18")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_events_empty_sprint_returns_400():
    """AC3: POST /events with sprint='' returns 400 and body has a non-empty 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="ac3_sprint_name", sprint="")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str) and len(body["error"]) > 0
    finally:
        conn.close()


@requires_db
def test_post_attempt_failed_returns_200_no_error():
    """AC1: POST /events with type 'attempt_failed' returns 200, Content-Type
    application/json, and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="Sprint 18",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        event = {
            "api_version": "1",
            "card_id": "ac1_attempt",
            "type": "attempt_failed",
            "timestamp": "2024-01-12T14:00:00Z",
            "sprint": "Sprint 18",
            "attempt_number": 1,
            "failure_class": "parse",
            "failure_role": "Developer",
            "card": {"created": "2024-01-10"},
        }
        data = json.dumps(event).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/events",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())
        assert status == 200
        assert "application/json" in content_type
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_rate_zero_with_attempt_failed():
    """AC2: after started + attempt_failed + finished, GET /range returns
    first_attempt_rate_percent=0 and throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        attempt_failed = {
            "api_version": "1",
            "card_id": "ac2_attempt",
            "type": "attempt_failed",
            "timestamp": "2024-01-12T14:00:00Z",
            "sprint": "2024-06",
            "attempt_number": 1,
            "failure_class": "parse",
            "failure_role": "Developer",
            "card": {"created": "2024-01-10"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)

        finished = _make_event(
            card_id="ac2_attempt",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=2,
            failure_class="parse",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_rate_percent"] == 0
        assert body["sprints"]["2024-06"]["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_failure_breakdown_with_multiple_attempts():
    """AC3+UX6: after started + six attempt_failed + finished (attempts 7),
    GET /range returns first_attempt_rate_percent=0, throughput=1, and
    failure_breakdown with one entry per return (VERIFY 3, SCHEMA 2, TEST 1,
    all Developer) in count-descending order. top_failure_causes holds
    exactly three entries, one per (class, role) return pair."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_attempt'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac5_attempt",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        failure_classes = ["VERIFY", "SCHEMA", "VERIFY", "TEST", "SCHEMA", "VERIFY"]
        for i, fc in enumerate(failure_classes, start=1):
            event = {
                "api_version": "1",
                "card_id": "ac5_attempt",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": fc,
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac5_attempt",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=7,
            failure_class="VERIFY",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        sprint_data = body["sprints"]["2024-06"]
        assert sprint_data["first_attempt_rate_percent"] == 0
        assert sprint_data["throughput"] == 1
        assert sprint_data["failure_breakdown"] == [
            {"class": "VERIFY", "role": "Developer", "count": 3},
            {"class": "SCHEMA", "role": "Developer", "count": 2},
            {"class": "TEST", "role": "Developer", "count": 1},
        ]
        assert sprint_data["top_failure_causes"] == [
            {"class": "VERIFY", "role": "Developer", "count": 3},
            {"class": "SCHEMA", "role": "Developer", "count": 2},
            {"class": "TEST", "role": "Developer", "count": 1},
        ]
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_rate_driven_by_crew_attempts():
    """AC1: a card with started + two attempt_failed + finished (attempts 1)
    yields first_attempt_rate_percent 100 — the rate is driven by the
    crew-sent attempts on the finished row, not by 1 + count."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_crew_attempts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_crew_attempts",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ac1_crew_attempts",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac1_crew_attempts",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=1,
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_rate_percent"] == 100
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_rate_fallback_when_no_crew_attempts():
    """AC2: a card whose finished event carries no attempts field and whose
    history holds two attempt_failed rows yields first_attempt_rate_percent 0
    — the attempts count falls back to 1 + count (3)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_no_attempts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac2_no_attempts",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ac2_no_attempts",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ac2_no_attempts",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_rate_percent"] == 0
    finally:
        conn.close()


@requires_db
def test_sprint_first_attempt_numerator_denominator_crew_attempts():
    """UX7: a card with started + two attempt_failed + finished (attempts 1)
    yields first_attempt_numerator 1 and first_attempt_denominator 1, so the
    raw counts agree with the 100% rate and the crew-sent attempts count."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ux7_counts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ux7_counts",
            event_type="started",
            timestamp="2024-01-12T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ux7_counts",
                "type": "attempt_failed",
                "timestamp": f"2024-01-12T{10 + i}:00:00Z",
                "sprint": "2024-06",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2024-01-10"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ux7_counts",
            event_type="finished",
            timestamp="2024-01-16T10:00:00Z",
            sprint="2024-06",
            created="2024-01-10",
            attempts=1,
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        assert body["sprints"]["2024-06"]["first_attempt_numerator"] == 1
        assert body["sprints"]["2024-06"]["first_attempt_denominator"] == 1
    finally:
        conn.close()


@requires_db
def test_range_first_attempt_rate_crew_attempts():
    """UX8: a sprint with a card (started + two attempt_failed + finished
    attempts 1) included in a range yields first_attempt_rate_percent 100 —
    the crew's handout count drives the rate on the range surface as well."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ux8_range'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ux8_range",
            event_type="started",
            timestamp="2026-10-07T10:00:00Z",
            sprint="2026-10",
            created="2026-10-07",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        for i in (1, 2):
            event = {
                "api_version": "1",
                "card_id": "ux8_range",
                "type": "attempt_failed",
                "timestamp": f"2026-10-07T{10 + i}:00:00Z",
                "sprint": "2026-10",
                "attempt_number": i,
                "failure_class": "VERIFY",
                "failure_role": "Developer",
                "card": {"created": "2026-10-07"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", event)

        finished = _make_event(
            card_id="ux8_range",
            event_type="finished",
            timestamp="2026-10-10T10:00:00Z",
            sprint="2026-10",
            created="2026-10-07",
            attempts=1,
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        entry = body["sprints"]["2026-10"]
        assert entry["first_attempt_rate_percent"] == 100
    finally:
        conn.close()


@requires_db
def test_post_event_with_points_stores_value():
    """AC1+AC2+UX4: POST /events with card.points=5 returns 200, no error key,
    and SELECT points FROM board_events WHERE card_id='453' AND type='started'
    returns exactly one row whose points column holds the integer 5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = '453'")
    conn.commit()
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()
    conn.execute(
        "INSERT INTO sprint_metrics.sprints (name, start_date, end_date, timezone) "
        "VALUES ('Sprint 18', '2026-10-07', '2026-10-07', 'America/Chicago')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "453",
            "type": "started",
            "sprint": "Sprint 18",
            "timestamp": "2026-10-07T13:14:07Z",
            "card": {"created": "2026-10-07", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT points FROM sprint_metrics.board_events WHERE card_id = '453' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 5
    finally:
        conn.close()


@requires_db
def test_post_event_without_points_stores_null():
    """AC3+UX5: POST /events without card.points returns 200, no error key,
    and SELECT points FROM board_events WHERE card_id='455' AND type='started'
    returns exactly one row whose points column is NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = '455'")
    conn.commit()
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 18'")
    conn.commit()
    conn.execute(
        "INSERT INTO sprint_metrics.sprints (name, start_date, end_date, timezone) "
        "VALUES ('Sprint 18', '2026-10-07', '2026-10-07', 'America/Chicago')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "455",
            "type": "started",
            "sprint": "Sprint 18",
            "timestamp": "2026-10-07T09:15:00Z",
            "card": {"created": "2026-10-06"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT points FROM sprint_metrics.board_events WHERE card_id = '455' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        conn.close()


@requires_db
def test_range_registered_sprints_chronological_order():
    """AC1: Range with registered sprints whose lexicographic order differs from
    chronological order returns keys in start_date order."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac1_rs_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac1_rs_%'")
    conn.commit()

    upsert_sprint(conn, "ac1_rs_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac1_rs_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")
    upsert_sprint(conn, "ac1_rs_10", date(2024, 3, 1), date(2024, 3, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        for sprint, card_id in [
            ("ac1_rs_1", "ac1_rs_c1"),
            ("ac1_rs_2", "ac1_rs_c2"),
            ("ac1_rs_10", "ac1_rs_c3"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-03T10:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-07T15:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=ac1_rs_1&end=ac1_rs_10", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            raw_body = resp.read().decode()

        body = json.loads(raw_body)
        assert list(body["sprints"].keys()) == ["ac1_rs_1", "ac1_rs_2", "ac1_rs_10"]
    finally:
        conn.close()


@requires_db
def test_trend_registered_sprints_chronological_order():
    """AC2: Trend with registered sprints whose lexicographic order differs from
    chronological order returns values in start_date order."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac2_ts_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac2_ts_%'")
    conn.commit()

    upsert_sprint(conn, "ac2_ts_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac2_ts_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")
    upsert_sprint(conn, "ac2_ts_10", date(2024, 3, 1), date(2024, 3, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        for sprint, card_id in [
            ("ac2_ts_1", "ac2_ts_c1"),
            ("ac2_ts_2", "ac2_ts_c2"),
            ("ac2_ts_10", "ac2_ts_c3"),
        ]:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-03T10:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-07T15:00:00Z",
                    sprint=sprint,
                    created="2024-01-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=ac2_ts_1&end=ac2_ts_10"
        )
        assert status == 200
        assert body["values"][0]["sprint"] == "ac2_ts_1"
        assert body["values"][1]["sprint"] == "ac2_ts_2"
        assert body["values"][2]["sprint"] == "ac2_ts_10"
    finally:
        conn.close()


@requires_db
def test_range_registered_start_after_end_returns_400():
    """AC3: GET /range with registered sprints where start.start_date > end.start_date
    returns 400 with error referencing the invalid range."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name LIKE 'ac3_rs_%'")
    conn.commit()

    upsert_sprint(conn, "ac3_rs_1", date(2024, 1, 1), date(2024, 1, 14), "UTC")
    upsert_sprint(conn, "ac3_rs_2", date(2024, 2, 1), date(2024, 2, 14), "UTC")

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=ac3_rs_2&end=ac3_rs_1")
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str)
        assert "invalid range" in body["error"] or "ac3_rs_2" in body["error"]
    finally:
        conn.close()


@requires_db
def test_sprint_started_no_finished_returns_zeros():
    """AC1: a started event with no finished event returns zeros, not nulls."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_null'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-05'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_null",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-05",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-05&end=2024-05", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["sprints"]["2024-05"]["throughput"] == 0
        assert body["sprints"]["2024-05"]["cycle_time_days"] == 0
        assert body["sprints"]["2024-05"]["lead_time_days"] == 0
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_returns_all_nulls():
    """AC3 (UX): no events for the sprint returns all metrics null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2026-11&end=2026-11", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        sprint_data = body["sprints"]["2026-11"]
        assert sprint_data["throughput"] is None
        assert sprint_data["cycle_time_days"] is None
        assert sprint_data["lead_time_days"] is None
        assert sprint_data["failure_breakdown"] is None
        assert sprint_data["top_failure_causes"] is None
        assert sprint_data["flags"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_same_day_completion_with_failure_data():
    """AC4 (UX): same-day completion with failure data returns computed values, not nulls."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_null'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac4_null",
            event_type="started",
            timestamp="2026-10-07T13:14:07Z",
            sprint="2026-10",
            created="2026-10-07",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        finished = _make_event(
            card_id="ac4_null",
            event_type="finished",
            timestamp="2026-10-07T20:52:22Z",
            sprint="2026-10",
            created="2026-10-07",
            attempts=7,
            failure_class="VERIFY",
            failure_role="Developer",
        )
        _post_events(f"http://127.0.0.1:{port}/events", finished)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        sprint_data = body["sprints"]["2026-10"]
        assert sprint_data["throughput"] == 1
        assert sprint_data["cycle_time_days"] == 0
        assert isinstance(sprint_data["failure_breakdown"], list)
        assert len(sprint_data["failure_breakdown"]) == 1
        assert sprint_data["first_attempt_rate_percent"] == 0
    finally:
        conn.close()


@requires_db
def test_range_two_sprints_with_events_correct_metrics_and_prior():
    """AC1: Range with two known sprints returns correct throughput, cycle_time,
    prior, and delta in chronological order."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_range_ok_a', 'ac1_range_ok_b')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created 2024-01-01, started 2024-01-03, finished 2024-01-07
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: created 2024-02-01, started 2024-02-03, finished 2024-02-06
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_range_ok_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["2024-01", "2024-02"]
        assert sprints["2024-01"]["throughput"] == 1
        assert sprints["2024-01"]["cycle_time_days"] == 4
        assert sprints["2024-02"]["throughput"] == 1
        assert sprints["2024-02"]["cycle_time_days"] == 3
        assert sprints["2024-02"]["prior"]["throughput"] == 1
        assert sprints["2024-02"]["prior"]["cycle_time_days"] == 4
        assert sprints["2024-02"]["delta"]["throughput"] == 0
        assert sprints["2024-02"]["delta"]["cycle_time_days"] == -1
    finally:
        conn.close()


@requires_db
def test_range_single_sprint_prior_and_delta_null():
    """AC2: Range with one known sprint returns throughput=1, prior=null, delta=null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_range_single'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_single",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_range_single",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["2024-01"]
        assert sprints["2024-01"]["throughput"] == 1
        assert sprints["2024-01"]["prior"] is None
        assert sprints["2024-01"]["delta"] is None
    finally:
        conn.close()


@requires_db
def test_range_null_metrics_for_sprints_without_events():
    """AC3 (UX): Range spanning three sprints where only the first has events
    returns null metrics for the gap sprints and computed metrics for the known one."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_range_null_a'")
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_null_a",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_null_a",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # 2026-11 and 2026-12 have no events

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["2026-10", "2026-11", "2026-12"]
        assert sprints["2026-10"]["throughput"] == 1
        assert sprints["2026-11"]["throughput"] is None
        assert sprints["2026-11"]["cycle_time_days"] is None
        assert sprints["2026-11"]["failure_breakdown"] is None
        assert sprints["2026-12"]["throughput"] is None
        assert sprints["2026-11"]["cycle_time_minutes"] is None
        assert sprints["2026-11"]["lead_time_minutes"] is None
        assert sprints["2026-12"]["cycle_time_minutes"] is None
        assert sprints["2026-12"]["lead_time_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_known_sprint_after_unknown_prior_gets_null_prior_and_delta():
    """AC4 (UX): 2026-10 and 2026-12 have events, 2026-11 does not. The 2026-12
    entry has prior=null and delta=null because its preceding sprint is unknown."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_range_null_a', 'ac4_range_null_b')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_a",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_a",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # Sprint 2026-12: one completed card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_b",
                event_type="started",
                timestamp="2026-12-01T09:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_null_b",
                event_type="finished",
                timestamp="2026-12-03T15:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        # 2026-11 has no events

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2026-11"]["throughput"] is None
        assert sprints["2026-12"]["prior"] is None
        assert sprints["2026-12"]["delta"] is None
    finally:
        conn.close()


@requires_db
def test_trend_all_sprints_have_events_returns_integers():
    """AC1: GET /trend?metric=cycle_time_days&start=2024-01&end=2024-02 with events
    in both sprints returns 200, Content-Type application/json, and the values array
    has exactly 2 entries: 2024-01 value 4, 2024-02 value 3."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_trend_ok_a', 'ac1_trend_ok_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created 2024-01-01, started 2024-01-02, finished 2024-01-06 → cycle 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_a",
                event_type="started",
                timestamp="2024-01-02T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_a",
                event_type="finished",
                timestamp="2024-01-06T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: created 2024-02-01, started 2024-02-02, finished 2024-02-05 → cycle 3
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_b",
                event_type="started",
                timestamp="2024-02-02T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_trend_ok_b",
                event_type="finished",
                timestamp="2024-02-05T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 4}
        assert body["values"][1] == {"sprint": "2024-02", "value": 3}
    finally:
        conn.close()


@requires_db
def test_trend_gap_sprint_returns_null():
    """AC3: GET /trend?metric=cycle_time_days&start=2026-10&end=2026-12 with events
    in 2026-10 and 2026-12 but not 2026-11 returns 200, Content-Type application/json,
    values array has exactly 3 entries: 2026-10 value 4, 2026-11 value null, 2026-12 value 2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac3_trend_gap_a', 'ac3_trend_gap_b')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: created 2026-10-07, started 2026-10-07, finished 2026-10-11 → cycle 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_a",
                event_type="started",
                timestamp="2026-10-07T10:00:00Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_a",
                event_type="finished",
                timestamp="2026-10-11T15:00:00Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        # Sprint 2026-12: created 2026-12-01, started 2026-12-01, finished 2026-12-03 → cycle 2
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_b",
                event_type="started",
                timestamp="2026-12-01T10:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_trend_gap_b",
                event_type="finished",
                timestamp="2026-12-03T15:00:00Z",
                sprint="2026-12",
                created="2026-12-01",
            ),
        )
        # Sprint 2026-11: no events

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_days&start=2026-10&end=2026-12",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2026-10", "value": 4}
        assert body["values"][1] == {"sprint": "2026-11", "value": None}
        assert body["values"][2] == {"sprint": "2026-12", "value": 2}
    finally:
        conn.close()


@requires_db
def test_trend_single_sprint_with_events_returns_integer():
    """AC4: GET /trend?metric=throughput&start=2026-10&end=2026-10 with events in
    2026-10 returns 200, values array has exactly 1 entry, sprint 2026-10 value is
    integer 1 (not null)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_trend_single'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2026-10: one completed card, started and finished same day
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_trend_single",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_trend_single",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=throughput&start=2026-10&end=2026-10"
        )
        assert status == 200
        assert len(body["values"]) == 1
        assert body["values"][0]["sprint"] == "2026-10"
        assert body["values"][0]["value"] == 1
        assert isinstance(body["values"][0]["value"], int)
        assert not isinstance(body["values"][0]["value"], bool)
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_two_causes():
    """AC1: GET /range with two completed cards having distinct failure causes
    returns failure_breakdown with exactly two objects."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_fb_a', 'ac1_fb_b')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=3,
                failure_class="parse",
                failure_role="Developer",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_b",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_fb_b",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                attempts=2,
                failure_class="check",
                failure_role="Code Reviewer",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        fb = body["sprints"]["2024-01"]["failure_breakdown"]
        assert len(fb) == 2
        assert {"class": "parse", "role": "Developer", "count": 1} in fb
        assert {"class": "check", "role": "Code Reviewer", "count": 1} in fb
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_empty_when_first_attempt():
    """AC2: GET /range with a single completed card (attempts=1) returns
    failure_breakdown as an empty array."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac2_fb'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_fb",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac2_fb",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["failure_breakdown"] == []
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_not_truncated_to_three():
    """AC3 (UX): GET /range with four completed cards each having a distinct
    (failure_class, failure_role) pair returns failure_breakdown with exactly 4 objects."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac3_fb_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        cards = [
            ("ac3_fb_c1", "PARSE", "Code Reviewer", 3),
            ("ac3_fb_c2", "VERIFY", "Developer", 7),
            ("ac3_fb_c3", "SCHEMA", "Architect", 2),
            ("ac3_fb_c4", "SCHEMA", "Developer", 4),
        ]
        for card_id, fc, fr, attempts in cards:
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2026-10-07T13:14:07Z",
                    sprint="2026-10",
                    created="2026-10-07",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2026-10-07T20:52:22Z",
                    sprint="2026-10",
                    created="2026-10-07",
                    attempts=attempts,
                    failure_class=fc,
                    failure_role=fr,
                ),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        fb = body["sprints"]["2026-10"]["failure_breakdown"]
        assert len(fb) == 4
        assert {"class": "PARSE", "role": "Code Reviewer", "count": 1} in fb
        assert {"class": "VERIFY", "role": "Developer", "count": 1} in fb
        assert {"class": "SCHEMA", "role": "Architect", "count": 1} in fb
        assert {"class": "SCHEMA", "role": "Developer", "count": 1} in fb
    finally:
        conn.close()


@requires_db
def test_range_failure_breakdown_and_top_failure_causes_coexist():
    """AC4 (UX): GET /range with one completed card (VERIFY/Developer, attempts 7)
    returns both failure_breakdown (array with one object) and top_failure_causes
    (object with VERIFY mapping to 1)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac4_fb'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_fb",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_fb",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
                attempts=7,
                failure_class="VERIFY",
                failure_role="Developer",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        entry = body["sprints"]["2026-10"]
        assert entry["failure_breakdown"] == [{"class": "VERIFY", "role": "Developer", "count": 1}]
        assert entry["top_failure_causes"] == [{"class": "VERIFY", "role": "Developer", "count": 1}]
        assert len(entry["failure_breakdown"]) == 1
    finally:
        conn.close()


def _returned_event(card_id, sprint, timestamp, failure_class=None, failure_role=None):
    """A 'returned' event: the story handed back to the Business Analyst.

    failure_class (the reason) and failure_role (the step that sent it back) are
    optional top-level fields, as the crew sends them.
    """
    event = {
        "api_version": "1",
        "card_id": card_id,
        "type": "returned",
        "timestamp": timestamp,
        "sprint": sprint,
        "card": {"created": "2024-01-01"},
    }
    if failure_class is not None:
        event["failure_class"] = failure_class
    if failure_role is not None:
        event["failure_role"] = failure_role
    return event


@requires_db
def test_range_rework_names_each_sent_back_story_out_of_started():
    """AC1: a sprint in which 5 stories started and 2 were sent back (different
    steps and reasons) carries a rework answer naming each sent-back story by
    identifier, its step and its reason, out of the 5 started."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e1_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        for i in range(1, 6):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_e2e1_s{i}",
                    event_type="started",
                    timestamp=f"2024-03-0{i}T10:00:00Z",
                    sprint="2024-03",
                    created="2024-03-01",
                ),
            )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e1_s3",
                "2024-03",
                "2024-03-12T10:00:00Z",
                failure_class="contract_ruling",
                failure_role="Review",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e1_s4",
                "2024-03",
                "2024-03-13T10:00:00Z",
                failure_class="blocked_session",
                failure_role="QA",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        rework = body["sprints"]["2024-03"]["rework"]
        assert rework["started"] == 5
        assert rework["sent_backs"] == [
            {"card_id": "rw_e2e1_s3", "send_backs": [{"step": "Review", "reason": "contract_ruling"}]},
            {"card_id": "rw_e2e1_s4", "send_backs": [{"step": "QA", "reason": "blocked_session"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_step_is_unmodified_role_sent_on_event():
    """AC2: the rework step is the failure_role the crew sent on the returned
    event, unmodified — not a label the service invents."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e2_a",
                event_type="started",
                timestamp="2024-03-01T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e2_a",
                "2024-03",
                "2024-03-05T10:00:00Z",
                failure_class="reason",
                failure_role="Sprint 3's Team Lead",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        rework = body["sprints"]["2024-03"]["rework"]
        assert rework["sent_backs"][0]["send_backs"][0]["step"] == "Sprint 3's Team Lead"
    finally:
        conn.close()


@requires_db
def test_range_rework_counts_in_the_sprint_of_the_returned_event():
    """AC3: a story that started in sprint A and was sent back in sprint B is
    named in B's rework against B's started stories, and A's rework does not
    carry it."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e3_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-04', '2024-05')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Five stories start in 2024-04; one of them (rw_e2e3_m) is sent back in 2024-05.
        for i in range(1, 6):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_e2e3_s{i}",
                    event_type="started",
                    timestamp=f"2024-04-0{i}T10:00:00Z",
                    sprint="2024-04",
                    created="2024-04-01",
                ),
            )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e3_m",
                event_type="started",
                timestamp="2024-04-15T10:00:00Z",
                sprint="2024-04",
                created="2024-04-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e3_m",
                "2024-05",
                "2024-05-03T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-04&end=2024-05")
        assert status == 200
        sprints = body["sprints"]
        # A's rework names no sent-back story (it has events but no returned rows).
        assert sprints["2024-04"]["rework"]["started"] == 6
        assert sprints["2024-04"]["rework"]["sent_backs"] is None
        # B's rework names the send-back against B's started stories (0 started in B).
        assert sprints["2024-05"]["rework"]["started"] == 0
        assert sprints["2024-05"]["rework"]["sent_backs"] == [
            {
                "card_id": "rw_e2e3_m",
                "send_backs": [{"step": "Refinement", "reason": "story_problem"}],
            }
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_story_sent_back_twice_is_named_once():
    """AC4: a story sent back twice in the same sprint is named once, with both
    send-backs each carrying their step and reason, and it counts once in the
    out-of-started figure."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e4_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-06'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        for i in range(1, 5):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_e2e4_s{i}",
                    event_type="started",
                    timestamp=f"2024-06-0{i}T10:00:00Z",
                    sprint="2024-06",
                    created="2024-06-01",
                ),
            )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e4_s1",
                "2024-06",
                "2024-06-10T10:00:00Z",
                failure_class="contract_ruling",
                failure_role="Review",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e4_s1",
                "2024-06",
                "2024-06-12T10:00:00Z",
                failure_class="blocked_session",
                failure_role="QA",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-06&end=2024-06")
        assert status == 200
        rework = body["sprints"]["2024-06"]["rework"]
        assert rework["started"] == 4
        # The story is named once even though it was sent back twice.
        assert [entry["card_id"] for entry in rework["sent_backs"]] == ["rw_e2e4_s1"]
        assert rework["sent_backs"][0]["send_backs"] == [
            {"step": "Review", "reason": "contract_ruling"},
            {"step": "QA", "reason": "blocked_session"},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_lists_send_back_with_zero_started():
    """AC5: a sprint in which no story started but a story was sent back still
    lists the send-back and reads 0 started — it neither invents a proportion
    nor drops the send-back."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e5_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-07'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e5_x",
                "2024-07",
                "2024-07-03T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-07&end=2024-07")
        assert status == 200
        rework = body["sprints"]["2024-07"]["rework"]
        assert rework["started"] == 0
        assert rework["sent_backs"] == [
            {"card_id": "rw_e2e5_x", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]}
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_null_for_empty_sprint_and_no_data_without_returned():
    """AC6: a sprint with no events at all reads rework null (no data, not
    zero-filled); a sprint with events but no stored 'returned' events names no
    sent-back story and does not assert a zero send-back count."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e6_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-08', '2024-09')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # 2024-08 has events (one started+finished story); 2024-09 has none.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e6_a",
                event_type="started",
                timestamp="2024-08-03T10:00:00Z",
                sprint="2024-08",
                created="2024-08-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e6_a",
                event_type="finished",
                timestamp="2024-08-07T10:00:00Z",
                sprint="2024-08",
                created="2024-08-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-08&end=2024-09")
        assert status == 200
        sprints = body["sprints"]
        # The empty sprint reads no data, not a zero-filled answer.
        assert sprints["2024-09"]["rework"] is None
        assert sprints["2024-09"]["throughput"] is None
        # The events-but-no-returned sprint names no sent-back story (null, not
        # an empty list) and carries its started count.
        assert sprints["2024-08"]["rework"] == {"started": 1, "sent_backs": None}
    finally:
        conn.close()


@requires_db
def test_range_rework_changes_no_other_metric():
    """AC7: a sent-back story that is never re-completed changes none of the
    other metrics; the already-shipping keys keep their values and shape."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_e2e7_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # A story that starts and finishes (throughput 1, first attempt 100%).
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e7_done",
                event_type="started",
                timestamp="2024-10-03T10:00:00Z",
                sprint="2024-10",
                created="2024-10-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e7_done",
                event_type="finished",
                timestamp="2024-10-07T10:00:00Z",
                sprint="2024-10",
                created="2024-10-01",
            ),
        )
        status, before = _get_json(f"http://127.0.0.1:{port}/range?start=2024-10&end=2024-10")
        assert status == 200
        # A second story starts and is sent back to refinement, never re-completed.
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_e2e7_back",
                event_type="started",
                timestamp="2024-10-04T10:00:00Z",
                sprint="2024-10",
                created="2024-10-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_e2e7_back",
                "2024-10",
                "2024-10-06T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )
        status, after = _get_json(f"http://127.0.0.1:{port}/range?start=2024-10&end=2024-10")
        assert status == 200
        before_entry = {k: v for k, v in before["sprints"]["2024-10"].items() if k != "rework"}
        after_entry = {k: v for k, v in after["sprints"]["2024-10"].items() if k != "rework"}
        assert before_entry == after_entry
        # The send-back completes no story and adds no review/QA return.
        assert after_entry["throughput"] == 1
        assert after_entry["failure_breakdown"] == []
        assert after_entry["top_failure_causes"] == []
        assert after["sprints"]["2024-10"]["rework"]["sent_backs"] == [
            {"card_id": "rw_e2e7_back", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]}
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_qa_returns_named_separately_from_sent_backs():
    """AC1: a sprint in which one story was sent back to refinement and another
    was bounced at review (an attempt_failed on a completed card) carries a
    rework answer with two labeled parts, each naming its stories."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa1_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Story 1: sent back to refinement (returned event)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa1_s1",
                event_type="started",
                timestamp="2024-11-02T10:00:00Z",
                sprint="2024-11",
                created="2024-11-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_qa1_s1",
                "2024-11",
                "2024-11-05T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )
        # Story 2: bounced at review/QA (attempt_failed on a completed card)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa1_s2",
                event_type="started",
                timestamp="2024-11-03T10:00:00Z",
                sprint="2024-11",
                created="2024-11-01",
            ),
        )
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa1_s2",
            "type": "attempt_failed",
            "timestamp": "2024-11-06T10:00:00Z",
            "sprint": "2024-11",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2024-11-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa1_s2",
                event_type="finished",
                timestamp="2024-11-07T10:00:00Z",
                sprint="2024-11",
                created="2024-11-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-11&end=2024-11")
        assert status == 200
        rework = body["sprints"]["2024-11"]["rework"]
        assert rework["started"] == 2
        assert rework["sent_backs"] == [
            {"card_id": "rw_qa1_s1", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]},
        ]
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa1_s2", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_by_step_groups_each_part():
    """AC3: the rework answer's by_step shows the count of rework per step
    for each part, so the reader sees which step the sprint's rework
    concentrates in."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa2_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-12'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Two send-backs from different steps
        for i, (role, cls) in enumerate([("Review", "contract_ruling"), ("QA", "blocked_session")], start=1):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_qa2_s{i}",
                    event_type="started",
                    timestamp=f"2024-12-0{i}T10:00:00Z",
                    sprint="2024-12",
                    created="2024-12-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _returned_event(
                    f"rw_qa2_s{i}",
                    "2024-12",
                    f"2024-12-0{i}T12:00:00Z",
                    failure_class=cls,
                    failure_role=role,
                ),
            )
        # Two review/QA returns from the same step
        for i in (3, 4):
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_qa2_s{i}",
                    event_type="started",
                    timestamp=f"2024-12-0{i}T10:00:00Z",
                    sprint="2024-12",
                    created="2024-12-01",
                ),
            )
            attempt_failed = {
                "api_version": "1",
                "card_id": f"rw_qa2_s{i}",
                "type": "attempt_failed",
                "timestamp": f"2024-12-0{i}T12:00:00Z",
                "sprint": "2024-12",
                "attempt_number": 1,
                "failure_class": "parse_error",
                "failure_role": "QA",
                "card": {"created": "2024-12-01"},
            }
            _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=f"rw_qa2_s{i}",
                    event_type="finished",
                    timestamp=f"2024-12-0{i}T14:00:00Z",
                    sprint="2024-12",
                    created="2024-12-01",
                ),
            )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-12&end=2024-12")
        assert status == 200
        rework = body["sprints"]["2024-12"]["rework"]
        assert rework["by_step"] == {
            "sent_backs": {"Review": 1, "QA": 1},
            "qa_returns": {"QA": 2},
        }
    finally:
        conn.close()


@requires_db
def test_range_rework_qa_returns_only_no_sent_backs():
    """AC5: a sprint with review/QA returns but no send-backs carries
    sent_backs null and lists its qa_returns — the two parts do not
    borrow each other's data."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa3_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa3_s1",
                event_type="started",
                timestamp="2025-01-02T10:00:00Z",
                sprint="2025-01",
                created="2025-01-01",
            ),
        )
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa3_s1",
            "type": "attempt_failed",
            "timestamp": "2025-01-03T10:00:00Z",
            "sprint": "2025-01",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2025-01-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa3_s1",
                event_type="finished",
                timestamp="2025-01-04T10:00:00Z",
                sprint="2025-01",
                created="2025-01-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2025-01&end=2025-01")
        assert status == 200
        rework = body["sprints"]["2025-01"]["rework"]
        assert rework["started"] == 1
        assert rework["sent_backs"] is None
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa3_s1", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
        assert rework["by_step"] == {"qa_returns": {"Review": 1}}
    finally:
        conn.close()


@requires_db
def test_range_rework_story_in_both_parts_separately():
    """AC2: a story that both went back to the BA (returned event) and
    bounced at review/QA (attempt_failed on a completed card) appears in
    both parts, separately."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa4_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-02'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa4_s1",
                event_type="started",
                timestamp="2025-02-02T10:00:00Z",
                sprint="2025-02",
                created="2025-02-01",
            ),
        )
        # Bounced at review
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa4_s1",
            "type": "attempt_failed",
            "timestamp": "2025-02-03T10:00:00Z",
            "sprint": "2025-02",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2025-02-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        # Sent back to refinement
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _returned_event(
                "rw_qa4_s1",
                "2025-02",
                "2025-02-04T10:00:00Z",
                failure_class="story_problem",
                failure_role="Refinement",
            ),
        )
        # Completed
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa4_s1",
                event_type="finished",
                timestamp="2025-02-05T10:00:00Z",
                sprint="2025-02",
                created="2025-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2025-02&end=2025-02")
        assert status == 200
        rework = body["sprints"]["2025-02"]["rework"]
        # The story appears in both parts, separately
        assert rework["sent_backs"] == [
            {"card_id": "rw_qa4_s1", "send_backs": [{"step": "Refinement", "reason": "story_problem"}]},
        ]
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa4_s1", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_range_rework_failure_breakdown_unchanged():
    """AC4: the rework answer's qa_returns uses the same (failure class,
    returning role) values as failure_breakdown, and failure_breakdown
    keeps its values and shape."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'rw_qa5_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2025-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa5_s1",
                event_type="started",
                timestamp="2025-03-02T10:00:00Z",
                sprint="2025-03",
                created="2025-03-01",
            ),
        )
        attempt_failed = {
            "api_version": "1",
            "card_id": "rw_qa5_s1",
            "type": "attempt_failed",
            "timestamp": "2025-03-03T10:00:00Z",
            "sprint": "2025-03",
            "attempt_number": 1,
            "failure_class": "contract_ruling",
            "failure_role": "Review",
            "card": {"created": "2025-03-01"},
        }
        _post_events(f"http://127.0.0.1:{port}/events", attempt_failed)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="rw_qa5_s1",
                event_type="finished",
                timestamp="2025-03-04T10:00:00Z",
                sprint="2025-03",
                created="2025-03-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2025-03&end=2025-03")
        assert status == 200
        entry = body["sprints"]["2025-03"]
        # failure_breakdown keeps its shape and values
        assert entry["failure_breakdown"] == [
            {"class": "contract_ruling", "role": "Review", "count": 1},
        ]
        assert entry["top_failure_causes"] == [
            {"class": "contract_ruling", "role": "Review", "count": 1},
        ]
        # qa_returns uses the same (class, role) values
        rework = entry["rework"]
        assert rework["qa_returns"] == [
            {"card_id": "rw_qa5_s1", "returns": [{"step": "Review", "reason": "contract_ruling"}]},
        ]
    finally:
        conn.close()


@requires_db
def test_sprint_response_includes_points_first_attempt_and_escalation_count():
    """AC1/AC6: after POSTing started+finished+escalated for a card with points 5,
    GET /range returns the four new fields with correct values alongside existing keys."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_new_fields'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac1_new_fields",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            points=5,
        )
        finished = _make_event(
            card_id="ac1_new_fields",
            event_type="finished",
            timestamp="2024-01-07T15:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        escalated = _make_event(
            card_id="ac1_new_fields",
            event_type="escalated",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", finished)
        _post_events(f"http://127.0.0.1:{port}/events", escalated)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["points_delivered"] == 5
        assert sprint_data["first_attempt_numerator"] == 1
        assert sprint_data["first_attempt_denominator"] == 1
        assert "escalation_count" not in sprint_data
        assert "throughput" in sprint_data
        assert "first_attempt_rate_percent" in sprint_data
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_new_fields_are_null():
    """AC2/AC7: no events stored for sprint 2026-11, GET /range returns 200
    and the four new fields are null, matching the existing null pattern."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-11&end=2026-11")
        assert status == 200
        sprint_data = body["sprints"]["2026-11"]
        assert sprint_data["points_delivered"] is None
        assert sprint_data["first_attempt_numerator"] is None
        assert sprint_data["first_attempt_denominator"] is None
        assert "escalation_count" not in sprint_data
        assert sprint_data["throughput"] is None
        assert sprint_data["first_attempt_rate_percent"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_escalations_counted_without_completions():
    """AC3: one started event (no finished) and two escalated events for sprint 2024-01,
    GET /range returns points_delivered=0, first_attempt_numerator=0,
    first_attempt_denominator=0, escalation_count=2."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_esc'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started = _make_event(
            card_id="ac3_esc",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        esc1 = _make_event(
            card_id="ac3_esc",
            event_type="escalated",
            timestamp="2024-01-04T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        esc2 = _make_event(
            card_id="ac3_esc",
            event_type="escalated",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started)
        _post_events(f"http://127.0.0.1:{port}/events", esc1)
        _post_events(f"http://127.0.0.1:{port}/events", esc2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["points_delivered"] == 0
        assert sprint_data["first_attempt_numerator"] == 0
        assert sprint_data["first_attempt_denominator"] == 0
        assert "escalation_count" not in sprint_data
    finally:
        conn.close()


@requires_db
def test_range_includes_points_first_attempt_and_escalation_count():
    """AC4: 2024-01 has one finished card (points 5, attempts 1) and one escalated event;
    2024-02 has two finished cards (points 3 and 2, both attempts 1) and one escalated event.
    GET /range returns correct values per sprint with existing keys still present."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac4_range_a', 'ac4_range_b', 'ac4_range_c')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: one finished card (points 5, attempts 1)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                points=5,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_a",
                event_type="escalated",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: two finished cards (points 3 and 2, both attempts 1)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=3,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_c",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=2,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_c",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac4_range_b",
                event_type="escalated",
                timestamp="2024-02-05T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        s01 = body["sprints"]["2024-01"]
        s02 = body["sprints"]["2024-02"]
        # 2024-01: points 5, first-attempt 1/1, escalation 1
        assert s01["points_delivered"] == 5
        assert s01["first_attempt_numerator"] == 1
        assert s01["first_attempt_denominator"] == 1
        assert "escalation_count" not in s01
        # 2024-02: points 5 (3+2), first-attempt 2/2, escalation 1
        assert s02["points_delivered"] == 5
        assert s02["first_attempt_numerator"] == 2
        assert s02["first_attempt_denominator"] == 2
        assert "escalation_count" not in s02
        # Both entries still contain existing keys and prior and delta
        for s in (s01, s02):
            for key in ("throughput", "cycle_time_days", "prior", "delta"):
                assert key in s
    finally:
        conn.close()


@requires_db
def test_range_null_new_fields_for_sprints_without_events():
    """AC5: sprint 2026-10 has one finished card (points 2, attempts 1);
    sprints 2026-11 and 2026-12 have no stored events. GET /range returns
    2026-10 with values and 2026-11/2026-12 with nulls for the four new fields."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_range_null'")
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2026-10', '2026-11', '2026-12')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_null",
                event_type="started",
                timestamp="2026-10-07T13:14:07Z",
                sprint="2026-10",
                created="2026-10-07",
                points=2,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_range_null",
                event_type="finished",
                timestamp="2026-10-07T20:52:22Z",
                sprint="2026-10",
                created="2026-10-07",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-12")
        assert status == 200
        s10 = body["sprints"]["2026-10"]
        s11 = body["sprints"]["2026-11"]
        s12 = body["sprints"]["2026-12"]
        # 2026-10 has values
        assert s10["points_delivered"] == 2
        assert s10["first_attempt_numerator"] == 1
        assert s10["first_attempt_denominator"] == 1
        assert "escalation_count" not in s10
        # 2026-11 and 2026-12 have nulls
        for s in (s11, s12):
            assert s["points_delivered"] is None
            assert s["first_attempt_numerator"] is None
            assert s["first_attempt_denominator"] is None
            assert "escalation_count" not in s
    finally:
        conn.close()


@requires_db
def test_range_carries_no_escalation_keys_in_entry_prior_or_delta():
    """#774 AC1-AC3, AC5: with 2 escalated events and 1 completed card in the later
    sprint, /range carries no escalation key in any entry, prior or delta, keeps
    every kept measure, and an event-free sprint still answers null for them."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        events = [
            ("e1", "started", "2024-01-03T10:00:00Z", "2024-01"),
            ("e1", "finished", "2024-01-05T10:00:00Z", "2024-01"),
            ("e2", "started", "2024-02-03T10:00:00Z", "2024-02"),
            ("e2", "escalated", "2024-02-04T10:00:00Z", "2024-02"),
            ("e2", "escalated", "2024-02-05T10:00:00Z", "2024-02"),
            ("e2", "finished", "2024-02-06T10:00:00Z", "2024-02"),
        ]
        for event in events:
            status, _ = _post_events(f"http://127.0.0.1:{port}/events", _make_event(*event))
            assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-03")
        assert status == 200
        labels = ("2024-01", "2024-02", "2024-03")
        first, later, empty = (body["sprints"][label] for label in labels)
        assert first["prior"] is None and first["delta"] is None
        for part in (first, later, empty, later["prior"], later["delta"]):
            assert "escalation_rate_percent" not in part
            assert "escalation_count" not in part
        kept = (
            "cycle_time_days",
            "lead_time_days",
            "throughput",
            "wip_violations",
            "blocked_aging_days",
            "points_delivered",
            "first_attempt_numerator",
            "first_attempt_denominator",
            "first_attempt_rate_percent",
            "superseded_count",
            "superseded_points",
            "superseded_breakdown",
            "cycle_time_minutes",
            "lead_time_minutes",
            "failure_breakdown",
            "top_failure_causes",
            "story_costs",
            "cost",
        )
        for key in kept:
            assert key in later
        assert later["throughput"] == 1
        assert later["cycle_time_days"] == 3
        for key in ("cycle_time_days", "throughput", "points_delivered", "first_attempt_rate_percent"):
            assert empty[key] is None
    finally:
        conn.close()


@requires_db
def test_range_flags_do_not_depend_on_escalated_events():
    """#775 AC1, AC3: two sprints identical in every kept measure, one with 3
    escalated events, answer identical flags, each with exactly the eight kept
    measures and no escalation key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        events = []
        for sprint in ("2024-01", "2024-02"):
            card = f"f-{sprint}"
            events.append((card, "started", f"{sprint}-03T10:00:00Z", sprint, f"{sprint}-01"))
            events.append((card, "finished", f"{sprint}-05T10:00:00Z", sprint, f"{sprint}-01"))
        for hour in ("11", "12", "13"):
            timestamp = f"2024-02-04T{hour}:00:00Z"
            events.append(("f-2024-02", "escalated", timestamp, "2024-02", "2024-02-01"))
        for event in events:
            status, _ = _post_events(f"http://127.0.0.1:{port}/events", _make_event(*event))
            assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        quiet, escalated = body["sprints"]["2024-01"]["flags"], body["sprints"]["2024-02"]["flags"]
        assert quiet == escalated
        assert sorted(escalated) == sorted(
            [
                "cycle_time_days",
                "lead_time_days",
                "cycle_time_minutes",
                "lead_time_minutes",
                "throughput",
                "wip_violations",
                "blocked_aging_days",
                "first_attempt_rate_percent",
            ]
        )
    finally:
        conn.close()


@requires_db
@pytest.mark.parametrize("metric", ["escalation_rate_percent", "escalation_count"])
def test_trend_refuses_the_escalation_measures(metric):
    """#776 AC1: GET /trend for either escalation measure answers 400 naming the
    measure and saying it is no longer accepted, with no retryable flag."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric={metric}&start=2024-01&end=2024-02"
        )
        assert status == 400
        assert metric in body["error"]
        assert "no longer accepted" in body["error"]
        assert "retryable" not in body
    finally:
        conn.close()


@requires_db
def test_trend_answers_api_version_4_and_still_refuses_escalation_count():
    """#778 AC2: a kept-metric /trend answers 200 with api_version "4" and null
    for an event-free sprint, and escalation_count still answers 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        for event in (
            ("v1", "started", "2024-01-03T10:00:00Z"),
            ("v1", "finished", "2024-01-05T10:00:00Z"),
        ):
            assert _post_events(f"{base}/events", _make_event(*event))[0] == 200
        status, body = _get_json(f"{base}/trend?metric=throughput&start=2024-01&end=2024-02")
        assert status == 200
        assert body["api_version"] == "4"
        assert body["values"] == [
            {"sprint": "2024-01", "value": 1},
            {"sprint": "2024-02", "value": None},
        ]
        status, _ = _get_json(f"{base}/trend?metric=escalation_count&start=2024-01&end=2024-02")
        assert status == 400
    finally:
        conn.close()


def test_trend_accepts_no_escalation_measure():
    """#776 AC3, AC4: neither escalation name is an accepted trend metric, and the
    /trend endpoint description no longer lists them."""
    from sprint_metrics.metrics import ALL_METRICS
    from sprint_metrics.service import SERVICE_ENDPOINTS

    assert "escalation_rate_percent" not in ALL_METRICS
    assert "escalation_count" not in ALL_METRICS
    trend = next(desc for method, path, desc in SERVICE_ENDPOINTS if path == "/trend")
    assert "escalation" not in trend


@requires_db
def test_escalated_event_is_stored_but_feeds_no_response():
    """#777 AC3: an escalated event is accepted and stored as before, but no
    /range field and no kept /trend value depends on it."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        for event in (
            ("x1", "started", "2024-01-03T10:00:00Z"),
            ("x1", "finished", "2024-01-05T10:00:00Z"),
        ):
            assert _post_events(f"{base}/events", _make_event(*event))[0] == 200
        _, range_before = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        _, trend_before = _get_json(f"{base}/trend?metric=throughput&start=2024-01&end=2024-01")

        escalated = _make_event("x1", "escalated", "2024-01-04T10:00:00Z")
        assert _post_events(f"{base}/events", escalated) == (200, {})
        stored = conn.execute(
            "SELECT COUNT(*) FROM sprint_metrics.board_events WHERE type = 'escalated'"
        ).fetchone()[0]
        assert stored == 1

        _, range_after = _get_json(f"{base}/range?start=2024-01&end=2024-01")
        _, trend_after = _get_json(f"{base}/trend?metric=throughput&start=2024-01&end=2024-01")
        assert range_after == range_before
        assert trend_after == trend_before
        assert "escalation_count" not in range_after["sprints"]["2024-01"]
    finally:
        conn.close()


@requires_db
def test_trend_points_delivered_two_sprints():
    """AC1+AC5: GET /trend?metric=points_delivered&start=2024-01&end=2024-02 with
    sprint 2024-01 having one finished card (points 5) and sprint 2024-02 having
    two finished cards (points 3 and 4) returns 200, Content-Type application/json,
    and values array has exactly two entries in order: 2024-01 value 5, 2024-02 value 7."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN "
        "('ac1_pd_a', 'ac1_pd_b', 'ac1_pd_c')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: one finished card with points 5
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                points=5,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_a",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        # Sprint 2024-02: two finished cards with points 3 and 4
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_b",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=3,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_b",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_c",
                event_type="started",
                timestamp="2024-02-03T10:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
                points=4,
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_pd_c",
                event_type="finished",
                timestamp="2024-02-06T15:00:00Z",
                sprint="2024-02",
                created="2024-02-01",
            ),
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=points_delivered&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "4"
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 5}
        assert body["values"][1] == {"sprint": "2024-02", "value": 7}
    finally:
        conn.close()


@requires_db
def test_trend_first_attempt_denominator_two_sprints():
    """AC2: GET /trend?metric=first_attempt_denominator&start=2024-01&end=2024-02 with
    sprint 2024-01 having three finished cards and sprint 2024-02 having five finished
    cards returns 200 and values has 2024-01 value 3 and 2024-02 value 5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id LIKE 'ac2_fa_%'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: three finished cards
        for i in range(3):
            card_id = f"ac2_fa_{chr(ord('a') + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-01-03T10:00:00Z",
                    sprint="2024-01",
                    created="2024-01-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-01-07T15:00:00Z",
                    sprint="2024-01",
                    created="2024-01-01",
                ),
            )
        # Sprint 2024-02: five finished cards
        for i in range(5):
            card_id = f"ac2_fa_{chr(ord('a') + 3 + i)}"
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="started",
                    timestamp="2024-02-03T10:00:00Z",
                    sprint="2024-02",
                    created="2024-02-01",
                ),
            )
            _post_events(
                f"http://127.0.0.1:{port}/events",
                _make_event(
                    card_id=card_id,
                    event_type="finished",
                    timestamp="2024-02-06T15:00:00Z",
                    sprint="2024-02",
                    created="2024-02-01",
                ),
            )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=first_attempt_denominator"
            f"&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 3}
        assert body["values"][1] == {"sprint": "2024-02", "value": 5}
    finally:
        conn.close()


@requires_db
def test_post_superseded_stores_full_metadata():
    """AC1: POST /events with type='superseded' stores because, epic, and replaced_by."""
    import json as json_mod

    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c9'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c9",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
            "epic": "Fix auth flow",
            "replaced_by": [480, 481],
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT because, epic, replaced_by FROM sprint_metrics.board_events "
            "WHERE card_id = 'c9' AND type = 'superseded'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "sponsor"
        assert rows[0][1] == "Fix auth flow"
        replaced = rows[0][2]
        if isinstance(replaced, str):
            replaced = json_mod.loads(replaced)
        assert replaced == [480, 481]
    finally:
        conn.close()


@requires_db
def test_post_superseded_invalid_because_returns_400():
    """AC3: POST /events with type='superseded' and because='invalid_reason' returns 400
    with an error naming the invalid value."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c9",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "invalid_reason",
            "epic": "Fix auth flow",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "invalid_reason" in body["error"]
    finally:
        conn.close()


@requires_db
def test_post_superseded_without_replaced_by_stores_null():
    """AC1: POST /events with type='superseded' and no replaced_by field returns 200,
    no error key, and the stored row has replaced_by column NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c10",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "story_problem",
            "epic": "Fix auth flow",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT replaced_by FROM sprint_metrics.board_events "
            "WHERE card_id = 'c10' AND type = 'superseded'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        conn.close()


@requires_db
def test_post_superseded_replaced_by_not_array_returns_400():
    """AC3: POST /events with type='superseded' and replaced_by='not_an_array' (a string)
    returns 400 with a non-empty error string."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c12",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "sponsor",
            "epic": "Fix auth flow",
            "replaced_by": "not_an_array",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str) and len(body["error"]) > 0
    finally:
        conn.close()


@requires_db
def test_post_superseded_no_prior_events_returns_200():
    """AC2: POST /events with type='superseded' for a card with no prior events
    returns 200 and body has no 'error' key."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c11",
            "type": "superseded",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "because": "sponsor",
            "epic": "Fix auth flow",
            "replaced_by": [500],
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_post_returned_stores_failure_class_role_and_epic():
    """AC1: POST /events with type='returned' carrying failure_class, failure_role,
    and epic answers 200 and the stored returned row carries all three values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'r1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "r1",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "failure_class": "blocked_session",
            "failure_role": "review",
            "epic": "epic-7",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT failure_class, failure_role, epic FROM sprint_metrics.board_events "
            "WHERE card_id = 'r1' AND type = 'returned'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "blocked_session"
        assert rows[0][1] == "review"
        assert rows[0][2] == "epic-7"
    finally:
        conn.close()


@requires_db
def test_post_returned_without_optional_fields_stores_null():
    """AC2: POST /events with type='returned' and no failure_class, failure_role, or
    epic answers 200 and stores those columns as NULL."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'r2'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "r2",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT failure_class, failure_role, epic FROM sprint_metrics.board_events "
            "WHERE card_id = 'r2' AND type = 'returned'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
        assert rows[0][1] is None
        assert rows[0][2] is None
    finally:
        conn.close()


@requires_db
def test_post_returned_resend_fills_null_keeps_existing():
    """AC3: re-sending a stored 'returned' event with a failure_class the first send
    left NULL answers 200; the NULL field takes the supplied value and fields that
    already hold a value are not changed."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'r3'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        first = {
            "api_version": "1",
            "card_id": "r3",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "failure_role": "review",
            "epic": "epic-7",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", first)
        assert status == 200
        assert "error" not in body

        resend = {
            "api_version": "1",
            "card_id": "r3",
            "type": "returned",
            "sprint": "2024-01",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-01"},
            "failure_class": "blocked_session",
            "failure_role": "qa",
            "epic": "epic-9",
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", resend)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT failure_class, failure_role, epic FROM sprint_metrics.board_events "
            "WHERE card_id = 'r3' AND type = 'returned'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "blocked_session"
        assert rows[0][1] == "review"
        assert rows[0][2] == "epic-7"
    finally:
        conn.close()


@requires_db
def test_post_unknown_event_type_returns_400_naming_type():
    """AC4: POST /events with a type that is not one of the eight accepted event
    types answers 400 naming the unknown type."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        event = _make_event(card_id="r4", event_type="reopened")
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert "reopened" in body["error"]
    finally:
        conn.close()


@requires_db
def test_range_single_named_sprint_registered_returns_200():
    """AC1: GET /range?start=Sprint%206&end=Sprint%206 with Sprint 6 registered
    returns 200 and the sprints object has exactly one key, 'Sprint 6'."""
    from datetime import date

    import psycopg

    from sprint_metrics.store import upsert_sprint

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 6'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = 'Sprint 6'")
    conn.commit()

    upsert_sprint(conn, "Sprint 6", date(2024, 3, 4), date(2024, 3, 15), "UTC")

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_named_single",
                event_type="started",
                timestamp="2024-03-05T10:00:00Z",
                sprint="Sprint 6",
                created="2024-03-04",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_named_single",
                event_type="finished",
                timestamp="2024-03-08T15:00:00Z",
                sprint="Sprint 6",
                created="2024-03-04",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=Sprint%206&end=Sprint%206")
        assert status == 200
        sprints = body["sprints"]
        assert list(sprints.keys()) == ["Sprint 6"]
    finally:
        conn.close()


@requires_db
def test_range_single_named_sprint_unregistered_returns_400():
    """AC2: GET /range?start=Sprint%206&end=Sprint%206 with Sprint 6 NOT registered
    returns 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.sprints WHERE name = 'Sprint 6'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = 'Sprint 6'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=Sprint%206&end=Sprint%206")
        assert status == 400
        assert "error" in body
    finally:
        conn.close()


class _FakeSprintCursor:
    """Minimal cursor that returns pre-loaded rows from fetchall."""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSprintConn:
    """In-memory stand-in for a psycopg connection, sufficient for
    store.resolve_sprint_range. No database or SPRINT_METRICS_DB required."""

    def __init__(self, sprints):
        self._sprints = sprints

    def execute(self, sql, params=()):
        if "start_date BETWEEN" in sql:
            lo, hi = params
            names = sorted(
                (name for name, sd in self._sprints.items() if lo <= sd <= hi),
                key=lambda name: (self._sprints[name], name),
            )
            rows = [(name,) for name in names]
        else:
            wanted = set(params)
            rows = [(name, sd) for name, sd in self._sprints.items() if name in wanted]
        return _FakeSprintCursor(rows)


def test_resolve_sprint_range_single_named_sprint_returns_that_sprint():
    """AC1: a range of one registered sprint (start == end) resolves to that
    sprint, not None. Fails against the old len(rows) < 2 guard that made a
    single-sprint range look unregistered."""
    from datetime import date

    from sprint_metrics.store import resolve_sprint_range

    conn = _FakeSprintConn({"Sprint 6": date(2024, 3, 4)})
    assert resolve_sprint_range(conn, "Sprint 6", "Sprint 6") == ["Sprint 6"]


def test_resolve_sprint_range_single_unregistered_sprint_returns_none():
    """AC2: a range of one non-registered name still resolves to None (the 400
    path), so the calendar-month fallback is reached rather than a silent
    single-sprint answer."""
    from sprint_metrics.store import resolve_sprint_range

    conn = _FakeSprintConn({})
    assert resolve_sprint_range(conn, "Sprint 6", "Sprint 6") is None


@requires_db
def test_sprint_superseded_metrics_with_mixed_events():
    """AC1: GET /range returns superseded_count, superseded_points,
    superseded_breakdown from stored superseded events; superseded card
    excluded from throughput."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('sup_c1', 'sup_c2')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="sup_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-02",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "sup_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-02", "points": 5},
            "because": "sponsor",
        }
        finished_c2 = _make_event(
            card_id="sup_c2",
            event_type="finished",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            started="2024-01-02",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c2)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["superseded_count"] == 1
        assert sprint_data["superseded_points"] == 5
        assert sprint_data["superseded_breakdown"] == {"sponsor": 1, "story_problem": 0}
        assert sprint_data["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_range_superseded_metrics_per_sprint():
    """AC3: GET /range returns per-sprint superseded_count and superseded_points."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('rng_c1', 'rng_c2')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="rng_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "rng_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
        }
        started_c2 = _make_event(
            card_id="rng_c2",
            event_type="started",
            timestamp="2024-02-03T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        finished_c2 = _make_event(
            card_id="rng_c2",
            event_type="finished",
            timestamp="2024-02-07T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
            started="2024-02-02",
            points=3,
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", started_c2)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2024-01"]["superseded_count"] == 1
        assert sprints["2024-01"]["superseded_points"] == 5
        assert sprints["2024-02"]["superseded_count"] == 0
        assert sprints["2024-02"]["superseded_points"] == 0
    finally:
        conn.close()


@requires_db
def test_range_superseded_prior_and_delta():
    """AC4: GET /range prior and delta include superseded_count and superseded_points."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('rngd_c1', 'rngd_c2')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="rngd_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "rngd_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
        }
        started_c2 = _make_event(
            card_id="rngd_c2",
            event_type="started",
            timestamp="2024-02-03T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
        )
        finished_c2 = _make_event(
            card_id="rngd_c2",
            event_type="finished",
            timestamp="2024-02-07T10:00:00Z",
            sprint="2024-02",
            created="2024-02-01",
            started="2024-02-02",
            points=3,
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", started_c2)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c2)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2024-02"]["prior"]["superseded_count"] == 1
        assert sprints["2024-02"]["prior"]["superseded_points"] == 5
        assert sprints["2024-02"]["delta"]["superseded_count"] == -1
        assert sprints["2024-02"]["delta"]["superseded_points"] == -5
    finally:
        conn.close()


@requires_db
def test_sprint_superseded_excluded_from_throughput():
    """AC5: A superseded card is not counted as delivered; throughput is 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'supt_c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="supt_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-02",
        )
        superseded_c1 = {
            "api_version": "1",
            "card_id": "supt_c1",
            "type": "superseded",
            "timestamp": "2024-01-04T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-02", "points": 5},
            "because": "sponsor",
        }
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["throughput"] == 0
        assert body["sprints"]["2024-01"]["superseded_count"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_multiple_superseded_breakdown():
    """AC7: Two superseded cards (sponsor, story_problem) plus one finished card
    produce superseded_count=2, superseded_points=8, correct breakdown, throughput=1."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('sup2_c1', 'sup2_c2', 'sup2_c3')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        superseded_c1 = {
            "api_version": "1",
            "card_id": "sup2_c1",
            "type": "superseded",
            "timestamp": "2024-01-03T10:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 5},
            "because": "sponsor",
        }
        superseded_c2 = {
            "api_version": "1",
            "card_id": "sup2_c2",
            "type": "superseded",
            "timestamp": "2024-01-03T11:00:00Z",
            "sprint": "2024-01",
            "card": {"created": "2024-01-01", "points": 3},
            "because": "story_problem",
        }
        finished_c3 = _make_event(
            card_id="sup2_c3",
            event_type="finished",
            timestamp="2024-01-05T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
            started="2024-01-02",
        )
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c1)
        _post_events(f"http://127.0.0.1:{port}/events", superseded_c2)
        _post_events(f"http://127.0.0.1:{port}/events", finished_c3)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01", timeout=5
        ) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Type", "") == "application/json"
            body = json.loads(resp.read().decode())

        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["superseded_count"] == 2
        assert sprint_data["superseded_points"] == 8
        assert sprint_data["superseded_breakdown"] == {"sponsor": 1, "story_problem": 1}
        assert sprint_data["throughput"] == 1
    finally:
        conn.close()


@requires_db
def test_sprint_only_started_superseded_zeros_not_null():
    """AC8: A sprint with only a started event (no superseded, no finished)
    returns integer zeros for superseded fields, not null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'zero_c1'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        started_c1 = _make_event(
            card_id="zero_c1",
            event_type="started",
            timestamp="2024-01-03T10:00:00Z",
            sprint="2024-01",
            created="2024-01-01",
        )
        _post_events(f"http://127.0.0.1:{port}/events", started_c1)

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["superseded_count"] == 0
        assert sprint_data["superseded_points"] == 0
        assert sprint_data["superseded_breakdown"] == {"sponsor": 0, "story_problem": 0}
        assert sprint_data["throughput"] == 0
        assert isinstance(sprint_data["superseded_count"], int)
        assert isinstance(sprint_data["superseded_points"], int)
        assert isinstance(sprint_data["superseded_breakdown"], dict)
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_superseded_fields_null():
    """AC2: A sprint with no events returns null for superseded_count,
    superseded_points, and superseded_breakdown."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-11'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-11&end=2026-11")
        assert status == 200
        sprint_data = body["sprints"]["2026-11"]
        assert sprint_data["superseded_count"] is None
        assert sprint_data["superseded_points"] is None
        assert sprint_data["superseded_breakdown"] is None
    finally:
        conn.close()


@requires_db
def test_trend_superseded_count_three_sprints():
    """AC1: GET /trend?metric=superseded_count&start=2024-01&end=2024-03 with
    a superseded event for card c1 in sprint 2024-01 (because "sponsor", points 5)
    and a superseded event for card c2 in sprint 2024-02 (because "story_problem",
    points 3) returns 200, Content-Type application/json, and values array has
    exactly three entries in order: 2024-01 value 1, 2024-02 value 1, 2024-03 value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac1_sup_c1', 'ac1_sup_c2')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02', '2024-03')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: superseded event for card c1 (because "sponsor", points 5)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac1_sup_c1",
                "type": "superseded",
                "sprint": "2024-01",
                "timestamp": "2024-01-15T10:00:00Z",
                "card": {"created": "2024-01-01", "points": 5},
                "because": "sponsor",
            },
        )
        # Sprint 2024-02: superseded event for card c2 (because "story_problem", points 3)
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac1_sup_c2",
                "type": "superseded",
                "sprint": "2024-02",
                "timestamp": "2024-02-15T10:00:00Z",
                "card": {"created": "2024-02-01", "points": 3},
                "because": "story_problem",
            },
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=superseded_count&start=2024-01&end=2024-03",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert body["api_version"] == "4"
        assert len(body["values"]) == 3
        assert body["values"][0] == {"sprint": "2024-01", "value": 1}
        assert body["values"][1] == {"sprint": "2024-02", "value": 1}
        assert body["values"][2] == {"sprint": "2024-03", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_points_two_sprints():
    """AC2: GET /trend?metric=superseded_points&start=2024-01&end=2024-02 with
    a superseded event for card c1 in sprint 2024-01 (points 5) and card c2 in
    sprint 2024-02 (points 3) returns 200 with values array having two entries:
    2024-01 value 5 and 2024-02 value 3."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac2_sup_c1', 'ac2_sup_c2')"
    )
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac2_sup_c1",
                "type": "superseded",
                "sprint": "2024-01",
                "timestamp": "2024-01-15T10:00:00Z",
                "card": {"created": "2024-01-01", "points": 5},
                "because": "sponsor",
            },
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac2_sup_c2",
                "type": "superseded",
                "sprint": "2024-02",
                "timestamp": "2024-02-15T10:00:00Z",
                "card": {"created": "2024-02-01", "points": 3},
                "because": "story_problem",
            },
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=superseded_points&start=2024-01&end=2024-02",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 5}
        assert body["values"][1] == {"sprint": "2024-02", "value": 3}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_count_empty_db_returns_nulls():
    """AC4: GET /trend?metric=superseded_count&start=2024-01&end=2024-02 on an
    empty DB returns 200 with values array having two entries both with value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=superseded_count&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_count_four_sprints_with_gap():
    """AC6 (UX): GET /trend?metric=superseded_count&start=2024-01&end=2024-04 with
    events in 2024-01 and 2024-03 but not 2024-02 or 2024-04 returns 200,
    Content-Type application/json, and values array has exactly four entries in
    order: 2024-01 value 1, 2024-02 value null, 2024-03 value 1, 2024-04 value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac6_sup_c1', 'ac6_sup_c2')"
    )
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE sprint IN "
        "('2024-01', '2024-02', '2024-03', '2024-04')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: superseded event for card c1
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac6_sup_c1",
                "type": "superseded",
                "sprint": "2024-01",
                "timestamp": "2024-01-15T10:00:00Z",
                "card": {"created": "2024-01-01", "points": 5},
                "because": "sponsor",
            },
        )
        # Sprint 2024-03: superseded event for card c2
        _post_events(
            f"http://127.0.0.1:{port}/events",
            {
                "api_version": "1",
                "card_id": "ac6_sup_c2",
                "type": "superseded",
                "sprint": "2024-03",
                "timestamp": "2024-03-15T10:00:00Z",
                "card": {"created": "2024-03-01", "points": 3},
                "because": "story_problem",
            },
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/trend?metric=superseded_count&start=2024-01&end=2024-04",
            timeout=5,
        ) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            body = json.loads(resp.read().decode())

        assert len(body["values"]) == 4
        assert body["values"][0] == {"sprint": "2024-01", "value": 1}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert body["values"][2] == {"sprint": "2024-03", "value": 1}
        assert body["values"][3] == {"sprint": "2024-04", "value": None}
    finally:
        conn.close()


@requires_db
def test_trend_superseded_points_empty_db_returns_nulls():
    """AC7 (UX): GET /trend?metric=superseded_points&start=2024-01&end=2024-02 on
    an empty DB returns 200 with values array having exactly two entries both
    with value null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=superseded_points&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": None}
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
    finally:
        conn.close()


@requires_db
def test_post_event_with_created_at_stores_timestamp():
    """AC1+AC5: POST /events with card.created_at stores the timestamp in card_created_at."""
    from datetime import datetime

    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_subday'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c_subday",
            "type": "started",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-10", "created_at": "2024-01-10T08:30:00Z", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT card_created_at FROM sprint_metrics.board_events "
            "WHERE card_id = 'c_subday' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        expected = datetime(2024, 1, 10, 8, 30, 0, tzinfo=UTC)
        assert rows[0][0] == expected
    finally:
        conn.close()


@requires_db
def test_post_event_without_created_at_stores_null():
    """AC2+AC6: POST /events without card.created_at stores NULL in card_created_at."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_no_created_at'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c_no_created_at",
            "type": "started",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-10"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body

        rows = conn.execute(
            "SELECT card_created_at FROM sprint_metrics.board_events "
            "WHERE card_id = 'c_no_created_at' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        conn.close()


@requires_db
def test_post_event_with_invalid_created_at_returns_400():
    """AC3: POST /events with unparseable card.created_at returns 400 with error."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_bad_ts'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = {
            "api_version": "1",
            "card_id": "c_bad_ts",
            "type": "started",
            "sprint": "Sprint 19",
            "timestamp": "2024-01-15T10:00:00Z",
            "card": {"created": "2024-01-10", "created_at": "not-a-timestamp"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "error" in body
        assert isinstance(body["error"], str)
        assert len(body["error"]) > 0
    finally:
        conn.close()


@requires_db
def test_sprint_cycle_and_lead_time_minutes_sub_day():
    """AC1: sub-day cycle and lead time returned as integer minutes via /sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac1_subday'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_subday",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac1_subday",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["cycle_time_minutes"] == 686
        assert sprint_data["cycle_time_days"] == 0
        assert sprint_data["lead_time_minutes"] == 3686
        assert sprint_data["lead_time_days"] == 2
    finally:
        conn.close()


@requires_db
def test_sprint_no_events_minute_fields_null():
    """AC2: /range with no stored events returns cycle_time_minutes and lead_time_minutes as null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-03'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-03&end=2024-03")
        assert status == 200
        sprint_data = body["sprints"]["2024-03"]
        assert sprint_data["cycle_time_minutes"] is None
        assert sprint_data["lead_time_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_range_cycle_and_lead_time_minutes_prior_and_delta():
    """AC3+AC4: /range returns cycle_time_minutes for populated sprint, null for gap sprint,
    prior carries the populated value, and delta is null for the gap sprint."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_range_min'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-01', '2024-02')")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_min",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_range_min",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-02")
        assert status == 200
        sprints = body["sprints"]
        assert sprints["2024-01"]["cycle_time_minutes"] == 686
        assert sprints["2024-01"]["lead_time_minutes"] == 3686
        assert sprints["2024-02"]["cycle_time_minutes"] is None
        assert sprints["2024-02"]["lead_time_minutes"] is None
        assert sprints["2024-02"]["prior"]["cycle_time_minutes"] == 686
        assert sprints["2024-02"]["prior"]["lead_time_minutes"] == 3686
        assert sprints["2024-02"]["delta"]["cycle_time_minutes"] is None
        assert sprints["2024-02"]["delta"]["lead_time_minutes"] is None
    finally:
        conn.close()


@requires_db
def test_sprint_same_day_card_minute_fields():
    """AC5: same-day card returns cycle_time_days=0, lead_time_days=0,
    cycle_time_minutes=30, lead_time_minutes=90 coexisting in the same response."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac5_sameday'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_sameday",
                event_type="started",
                timestamp="2024-01-03T09:00:00Z",
                sprint="2024-01",
                created="2024-01-03",
                created_at="2024-01-03T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac5_sameday",
                event_type="finished",
                timestamp="2024-01-03T09:30:00Z",
                sprint="2024-01",
                created="2024-01-03",
                created_at="2024-01-03T08:00:00Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        sprint_data = body["sprints"]["2024-01"]
        assert sprint_data["cycle_time_days"] == 0
        assert sprint_data["lead_time_days"] == 0
        assert sprint_data["cycle_time_minutes"] == 30
        assert sprint_data["lead_time_minutes"] == 90
    finally:
        conn.close()


@requires_db
def test_sprint_cycle_and_lead_time_minutes_rounding():
    """AC10: sub-day spans rounded to whole minutes: 685.87→686, 877.6→878."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac10_round'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2026-10'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac10_round",
                event_type="started",
                timestamp="2026-10-11T07:31:56Z",
                sprint="2026-10",
                created="2026-10-11",
                created_at="2026-10-11T04:20:12Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac10_round",
                event_type="finished",
                timestamp="2026-10-11T18:57:48Z",
                sprint="2026-10",
                created="2026-10-11",
                created_at="2026-10-11T04:20:12Z",
            ),
        )

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2026-10&end=2026-10")
        assert status == 200
        sprint_data = body["sprints"]["2026-10"]
        assert sprint_data["cycle_time_minutes"] == 686
        assert sprint_data["lead_time_minutes"] == 878
    finally:
        conn.close()


@requires_db
def test_trend_cycle_time_minutes_two_sprints():
    """AC1/UX4: GET /trend?metric=cycle_time_minutes returns 200 with integer values.

    Sprint 2024-01: started 10:00, finished 21:26 → 686 minutes.
    Sprint 2024-02: started 08:00, finished 10:30 → 150 minutes.
    """
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac_ctm_a', 'ac_ctm_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-03",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_a",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-03",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_b",
                event_type="started",
                timestamp="2024-02-05T08:00:00Z",
                sprint="2024-02",
                created="2024-02-05",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ctm_b",
                event_type="finished",
                timestamp="2024-02-05T10:30:00Z",
                sprint="2024-02",
                created="2024-02-05",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=cycle_time_minutes&start=2024-01&end=2024-02"
        )
        assert status == 200
        assert body["metric"] == "cycle_time_minutes"
        assert len(body["values"]) == 2
        assert body["values"][0] == {"sprint": "2024-01", "value": 686}
        assert body["values"][1] == {"sprint": "2024-02", "value": 150}
        assert isinstance(body["values"][0]["value"], int)
        assert isinstance(body["values"][1]["value"], int)
    finally:
        conn.close()


@requires_db
def test_trend_lead_time_minutes_gap_sprint_null():
    """AC2/UX5: GET /trend?metric=lead_time_minutes over three sprints where the
    middle sprint has no events: that sprint's value is JSON null."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute(
        "DELETE FROM sprint_metrics.board_events WHERE card_id IN ('ac_ltm_a', 'ac_ltm_b')"
    )
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Sprint 2024-01: created_at 2024-01-01T08:00:00Z, finished 2024-01-03T21:26:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_a",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_a",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        # Sprint 2024-03: created_at 2024-03-01T08:00:00Z, finished 2024-03-03T10:00:00Z
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_b",
                event_type="started",
                timestamp="2024-03-03T09:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
                created_at="2024-03-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_b",
                event_type="finished",
                timestamp="2024-03-03T10:00:00Z",
                sprint="2024-03",
                created="2024-03-01",
                created_at="2024-03-01T08:00:00Z",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=lead_time_minutes&start=2024-01&end=2024-03"
        )
        assert status == 200
        assert len(body["values"]) == 3
        assert body["values"][0]["sprint"] == "2024-01"
        assert isinstance(body["values"][0]["value"], int)
        assert body["values"][1] == {"sprint": "2024-02", "value": None}
        assert "value" in body["values"][1]
        assert body["values"][1]["value"] is None
        assert body["values"][2]["sprint"] == "2024-03"
        assert isinstance(body["values"][2]["value"], int)
    finally:
        conn.close()


@requires_db
def test_trend_lead_time_minutes_single_sprint_integer():
    """UX7: GET /trend?metric=lead_time_minutes&start=2024-01&end=2024-01 (single
    sprint) returns 200 with one entry whose value is a JSON integer."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac_ltm_single'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_single",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac_ltm_single",
                event_type="finished",
                timestamp="2024-01-03T21:26:00Z",
                sprint="2024-01",
                created="2024-01-01",
                created_at="2024-01-01T08:00:00Z",
            ),
        )

        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=lead_time_minutes&start=2024-01&end=2024-01"
        )
        assert status == 200
        assert len(body["values"]) == 1
        assert body["values"][0]["sprint"] == "2024-01"
        assert isinstance(body["values"][0]["value"], int)
    finally:
        conn.close()


@requires_db
def test_resend_event_fills_null_points_via_service():
    """AC3: POST /events without points, then with points=5: /range shows points_delivered=5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_svc'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event_no_points = {
            "api_version": "1",
            "card_id": "c_svc",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01"},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_no_points)
        assert status == 200

        event_with_points = {
            "api_version": "1",
            "card_id": "c_svc",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_with_points)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["points_delivered"] == 5
    finally:
        conn.close()


@requires_db
def test_resend_event_keeps_existing_points_via_service():
    """AC4: POST /events with points=5, then with points=3: /range shows points_delivered=5."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'c_svc2'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event_points_5 = {
            "api_version": "1",
            "card_id": "c_svc2",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01", "points": 5},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_points_5)
        assert status == 200

        event_points_3 = {
            "api_version": "1",
            "card_id": "c_svc2",
            "type": "finished",
            "sprint": "2024-01",
            "timestamp": "2024-01-07T15:00:00Z",
            "card": {"created": "2024-01-01", "points": 3},
        }
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event_points_3)
        assert status == 200

        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert body["sprints"]["2024-01"]["points_delivered"] == 5
    finally:
        conn.close()


@requires_db
def test_service_escalation_rate_200_on_sprint_range_and_trend():
    """AC3 (#774, #776): sprint 2024-01 has one completed card and 2 escalated
    events; /range carries no escalation rate and /trend refuses it with 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'ac3_esc_rate'")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint = '2024-01'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # Post started, finished, and 2 escalated events for one card
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="started",
                timestamp="2024-01-03T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="finished",
                timestamp="2024-01-07T15:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="escalated",
                timestamp="2024-01-05T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(
                card_id="ac3_esc_rate",
                event_type="escalated",
                timestamp="2024-01-06T10:00:00Z",
                sprint="2024-01",
                created="2024-01-01",
            ),
        )

        # /range
        status, body = _get_json(f"http://127.0.0.1:{port}/range?start=2024-01&end=2024-01")
        assert status == 200
        assert "escalation_rate_percent" not in body["sprints"]["2024-01"]

        # /trend
        status, body = _get_json(
            f"http://127.0.0.1:{port}/trend?metric=escalation_rate_percent&start=2024-01&end=2024-01"
        )
        assert status == 400
    finally:
        conn.close()


@requires_db
def test_finite_event_with_full_cost_payload_accepted():
    """AC1: POST a finished event with all five cost fields returns 200."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-a'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        # First, post a started event so the card exists
        _post_events(
            f"http://127.0.0.1:{port}/events",
            _make_event(card_id="cost-a", event_type="started", sprint="2024-01"),
        )
        # Now post a finished event with all five cost fields
        event = _make_event(
            card_id="cost-a",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_partial_cost_payload_rejected():
    """AC2: POST a finished event with only some cost fields returns 400,
    and the error identifies the cost payload as the problem."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-b'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-b",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
            cached_input_tokens=1400,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cost" in body["error"]
    finally:
        conn.close()


@requires_db
def test_negative_cost_field_rejected():
    """AC3a: POST a finished event with a negative cost field returns 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-c'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-c",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
            cached_input_tokens=-5,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cost" in body["error"]
    finally:
        conn.close()


@requires_db
def test_non_integer_cost_field_rejected():
    """AC3b: POST a finished event with a non-integer cost field returns 400."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-d'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-d",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500.5,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cost" in body["error"]
    finally:
        conn.close()


@requires_db
def test_finite_event_without_cost_fields_accepted():
    """AC4: POST a finished event with no cost fields returns 200, unchanged."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-e'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-e",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_schema_event_cost_properties_declared():
    """AC5: GET /schema/event's card object declares the five cost fields
    as integer properties with minimum 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card_props = body["properties"]["card"]["properties"]
        for field in (
            "model_seconds",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            assert field in card_props
            assert card_props[field]["type"] == "integer"
            assert card_props[field]["minimum"] == 0
    finally:
        conn.close()


@requires_db
def test_partial_cost_error_names_missing_fields():
    """UX7: The 400 response body's error message names the missing cost
    fields by their schema names."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'cost-ux'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="cost-ux",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=3500,
            input_tokens=4000,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "cached_input_tokens" in body["error"]
        assert "output_tokens" in body["error"]
        assert "reasoning_output_tokens" in body["error"]
    finally:
        conn.close()


@requires_db
def test_schema_event_card_required_unchanged():
    """UX8: The card object's required array is still exactly ['created']."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card = body["properties"]["card"]
        assert card["required"] == ["created"]
    finally:
        conn.close()


@requires_db
def test_finished_event_with_model_time_split_stores_values():
    """AC1: POST a finished event carrying the five cost fields plus a
    model-time split sub-object with refinement 1800 and delivery 3600.
    The response is 200 and the stored row carries the split values."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-a'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-a",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=5400,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-a' AND type = 'finished'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (1800, 3600)
    finally:
        conn.close()


@requires_db
def test_partial_model_time_split_rejected():
    """AC2: POST a finished event with a model-time split sub-object carrying
    only one of the two values returns 400, and the error identifies the
    model-time split as sent partially."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-b'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-b",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "model-time split" in body["error"]
        assert "partial" in body["error"]
        assert "delivery" in body["error"]
    finally:
        conn.close()


@requires_db
def test_model_time_split_string_value_rejected():
    """AC3a: POST a finished event with a model-time split value that is a
    string returns 400, and the error names the offending field."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-c'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-c",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": "abc", "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "refinement" in body["error"]
    finally:
        conn.close()


@requires_db
def test_model_time_split_negative_value_rejected():
    """AC3b: POST a finished event with a negative model-time split value
    returns 400, and the error names the offending field."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-d'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-d",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": -1, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 400
        assert "refinement" in body["error"]
    finally:
        conn.close()


@requires_db
def test_finished_event_cost_without_split_stores_null_split():
    """AC4a: POST a finished event with the five cost fields but no split
    sub-object returns 200, api_version stays '1', and the stored row has
    a null split."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-e'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-e",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_seconds=5400,
            input_tokens=4000,
            cached_input_tokens=1400,
            output_tokens=900,
            reasoning_output_tokens=300,
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        assert event["api_version"] == "1"
        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-e' AND type = 'finished'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (None, None)
    finally:
        conn.close()


@requires_db
def test_finished_event_split_without_cost_fields_accepted():
    """AC4b: POST a finished event carrying the split sub-object but none of
    the five cost fields is accepted (the split rides under its own
    all-or-nothing rule, separate from the five fields)."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-f'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-f",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
    finally:
        conn.close()


@requires_db
def test_started_event_with_split_not_stored():
    """AC5: POST a started event whose card carries a split sub-object
    returns 200 and the split is not stored."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-g'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-g",
            event_type="started",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200
        assert "error" not in body
        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-g' AND type = 'started'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (None, None)
    finally:
        conn.close()


@requires_db
def test_resend_finished_event_split_unchanged():
    """AC6: re-sending a stored finished event carrying a split with the same
    card_id, type and timestamp returns 200 and the stored split values are
    unchanged."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id = 'split-h'")
    conn.commit()

    port = _start_service(conn, 0)
    try:
        event = _make_event(
            card_id="split-h",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 1800, "delivery": 3600},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", event)
        assert status == 200

        # Re-send the same event with different split values
        resend = _make_event(
            card_id="split-h",
            event_type="finished",
            timestamp="2024-01-10T12:00:00Z",
            sprint="2024-01",
            model_time_split={"refinement": 9999, "delivery": 9999},
        )
        status, body = _post_events(f"http://127.0.0.1:{port}/events", resend)
        assert status == 200

        rows = conn.execute(
            "SELECT model_time_split_refinement, model_time_split_delivery "
            "FROM sprint_metrics.board_events "
            "WHERE card_id = 'split-h' AND type = 'finished'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (1800, 3600)
    finally:
        conn.close()


@requires_db
def test_schema_event_model_time_split_declared():
    """AC7: GET /schema/event declares the model_time_split sub-object with
    its two fields as required integers with minimum 0."""
    import psycopg

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)

    port = _start_service(conn, 0)
    try:
        status, body = _get_json(f"http://127.0.0.1:{port}/schema/event")
        assert status == 200
        card_props = body["properties"]["card"]["properties"]
        assert "model_time_split" in card_props
        split = card_props["model_time_split"]
        assert split["type"] == "object"
        assert split["required"] == ["refinement", "delivery"]
        assert split["properties"]["refinement"] == {"type": "integer", "minimum": 0}
        assert split["properties"]["delivery"] == {"type": "integer", "minimum": 0}
    finally:
        conn.close()
