"""Temporary debug: compare format_sprint_range_json with service inputs."""

from __future__ import annotations

import json

import psycopg
from test_idle_range import _register_sprint, _session_event
from test_service import (
    SPRINT_METRICS_DB,
    _get_json,
    _make_event,
    _post_events,
    _start_service,
    requires_db,
)
from sprint_metrics.sprint_range import format_sprint_range_json
from sprint_metrics.store import init_db, query_sprint


@requires_db
def test_debug_prior():
    from pathlib import Path

    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2025-05', '2025-06')")
    conn.execute("DELETE FROM sprint_metrics.sessions WHERE sprint IN ('2025-05', '2025-06')")
    conn.commit()
    _register_sprint(conn, "2025-05", "2025-05-01", "2025-05-14")
    _register_sprint(conn, "2025-06", "2025-06-01", "2025-06-14")

    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(
            f"{base}/events",
            _session_event("dga", "2025-05", "2025-05-05T10:00:00Z", "2025-05-05T10:30:00Z"),
        )
        _post_events(
            f"{base}/events",
            _make_event(
                card_id="dgb",
                event_type="started",
                timestamp="2025-06-05T10:00:00Z",
                sprint="2025-06",
            ),
        )
        # Direct formatter call with the service's inputs.
        sprints = {
            "2025-05": query_sprint(conn, "2025-05"),
            "2025-06": query_sprint(conn, "2025-06"),
        }
        body = json.loads(format_sprint_range_json(sprints, ["2025-05", "2025-06"]))
        direct = body["sprints"]["2025-06"]

        status, svc = _get_json(f"{base}/range?start=2025-05&end=2025-06")
        service = svc["sprints"]["2025-06"]

        Path(__file__).with_name("tmp_debug_out.json").write_text(
            f"direct prior_type={type(direct['prior']).__name__}\n"
            f"service prior_type={type(service['prior']).__name__}\n"
            f"sprints 2025-05 len={len(sprints['2025-05'])} 2025-06 len={len(sprints['2025-06'])}\n"
        )
    finally:
        conn.close()
