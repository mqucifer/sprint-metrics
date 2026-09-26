"""Tests for the scrape HTTP server in sprint_metrics.serve."""

import json
import urllib.error
import urllib.request


def test_serve_metrics_returns_port_and_serves_metrics(tmp_path):
    """AC1: a valid cards JSON file with one completed card. serve_metrics called
    from sprint_metrics.serve with that file path, no WIP limits, zero escalations,
    and port 0 returns an integer port greater than 0, and a GET request to
    http://127.0.0.1:{port}/metrics returns HTTP 200 with a body containing
    'sprint_cycle_time_days 4'."""
    from sprint_metrics.serve import serve_metrics

    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))

    port = serve_metrics(str(cards_path), None, 0, 0)
    assert isinstance(port, int)
    assert port > 0

    url = f"http://127.0.0.1:{port}/metrics"
    with urllib.request.urlopen(url, timeout=5) as response:
        status = response.status
        body = response.read().decode()

    assert status == 200
    assert "sprint_cycle_time_days 4" in body


def test_serve_metrics_returns_500_for_missing_file(tmp_path):
    """AC2: a cards file path pointing to a file that does not exist. serve_metrics
    called from sprint_metrics.serve with that path and port 0, and a GET request
    to the /metrics endpoint returns HTTP 500 with a body containing
    'sprint-metrics:'."""
    from sprint_metrics.serve import serve_metrics

    missing_path = str(tmp_path / "does-not-exist.json")

    port = serve_metrics(missing_path, None, 0, 0)
    assert isinstance(port, int)
    assert port > 0

    url = f"http://127.0.0.1:{port}/metrics"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.status
            body = response.read().decode()
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode()

    assert status == 500
    assert "sprint-metrics:" in body
