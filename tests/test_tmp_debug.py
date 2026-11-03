"""Temporary debug: check resolve_sprint_range vs query_range ordering."""

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
from sprint_metrics.store import (
    init_db,
    query_range,
    query_sprint,
    resolve_sprint_range,
)


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
        resolved = resolve_sprint_range(conn, "2025-05", "2025-06")
        range_dict = query_range(conn, "2025-05", "2025-06")
        Path(__file__).with_name("tmp_debug_out.json").write_text(
            f"resolved={resolved}\n"
            f"query_range keys={list(range_dict.keys())}\n"
        )
    finally:
        conn.close()
