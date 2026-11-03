"""Temporary debug: dump the /range response for two registered sprints where the
first has only session events and the second has only board events."""

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

from sprint_metrics.store import init_db


@requires_db
def test_debug_prior():
    from sprint_metrics.sprint_range import format_sprint_range_json

    from pathlib import Path

    body = format_sprint_range_json(
        {"2025-05": [], "2025-06": []}, ["2025-05", "2025-06"]
    )
    Path(__file__).with_name("tmp_debug_out.json").write_text(body)
    assert True
