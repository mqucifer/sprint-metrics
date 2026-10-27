import json

import psycopg
from sprint_metrics.store import init_db

from test_service import SPRINT_METRICS_DB, _get_json, _make_event, _post_events, _start_service


def test_debug():
    conn = psycopg.connect(SPRINT_METRICS_DB)
    init_db(conn)
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE card_id IN ('wtpd')")
    conn.execute("DELETE FROM sprint_metrics.board_events WHERE sprint IN ('2024-09', '2024-10')")
    conn.commit()
    port = _start_service(conn, 0)
    base = f"http://127.0.0.1:{port}"
    try:
        _post_events(base + "/events", _make_event(card_id="wtpd", event_type="started", timestamp="2024-10-02T09:00:00Z", sprint="2024-10"))
        _post_events(base + "/events", _make_event(card_id="wtpd", event_type="finished", timestamp="2024-10-02T10:00:00Z", sprint="2024-10"))
        status, body = _get_json(base + "/range?start=2024-09&end=2024-10")
        print("STATUS", status)
        e10 = body["sprints"]["2024-10"]
        print("KEYS", list(e10.keys()))
        print("PRIOR", json.dumps(e10.get("prior"), default=str))
        print("DELTA", json.dumps(e10.get("delta"), default=str))
        print("WORKING_TIME", json.dumps(e10.get("working_time"), default=str))
    finally:
        conn.close()
