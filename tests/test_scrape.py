"""Tests for the scrape endpoint that serves current sprint metrics."""

import json
import urllib.request

from sprint_metrics.crew_performance import main

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
IN_FLIGHT_CARD = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}


def _start_scrape_server(tmp_path, cards, wip_limits=None, escalations=0):
    """Write the cards file, start the scrape server in a thread, and return the URL."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    argv = [str(cards_path), "--scrape", "--port", "0"]
    if wip_limits is not None:
        limits_path = tmp_path / "wip-limits.json"
        limits_path.write_text(json.dumps(wip_limits))
        argv += ["--wip-limits", str(limits_path)]
    if escalations:
        argv += ["--escalations", str(escalations)]

    result = main(argv)
    # main returns the port number when in scrape mode
    port = result
    return f"http://127.0.0.1:{port}/metrics"


def _fetch(url):
    """Fetch a URL and return (status_code, body)."""
    with urllib.request.urlopen(url) as response:
        return response.status, response.read().decode()


def test_scrape_serves_cycle_time_lead_time_throughput_wip_blocked_escalation(tmp_path):
    """AC1: one completed card created 6 days before completion and started 4 days
    before completion, no WIP limits, no escalations. The /metrics endpoint returns
    HTTP 200 with all six metric lines at the expected values."""
    url = _start_scrape_server(tmp_path, [COMPLETED_CARD])
    status, body = _fetch(url)

    assert status == 200
    assert "sprint_cycle_time_days 4" in body
    assert "sprint_lead_time_days 6" in body
    assert "sprint_throughput_cards 1" in body
    assert "sprint_wip_violations 0" in body
    assert "sprint_blocked_aging_days 0" in body
    assert "sprint_escalation_rate_percent 0" in body


def test_scrape_reflects_updated_cards_file(tmp_path):
    """AC2: the scrape endpoint is running with one completed card. The cards file
    is updated to contain two completed cards. The next /metrics request returns
    HTTP 200 with sprint_throughput_cards 2."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([COMPLETED_CARD]))
    url = _start_scrape_server(tmp_path, [COMPLETED_CARD])

    # First request: one card
    status, body = _fetch(url)
    assert status == 200
    assert "sprint_throughput_cards 1" in body

    # Update the cards file to contain two completed cards
    cards_path.write_text(json.dumps([COMPLETED_CARD, COMPLETED_CARD]))

    # Second request: two cards
    status, body = _fetch(url)
    assert status == 200
    assert "sprint_throughput_cards 2" in body


def test_scrape_reports_wip_violation(tmp_path):
    """AC3: four in-flight cards with a WIP limit of 3 for In Progress. The
    /metrics endpoint returns HTTP 200 with sprint_wip_violations 1."""
    url = _start_scrape_server(tmp_path, [IN_FLIGHT_CARD] * 4, wip_limits={"In Progress": 3})
    status, body = _fetch(url)

    assert status == 200
    assert "sprint_wip_violations 1" in body


def test_scrape_reports_escalation_rate(tmp_path):
    """AC4: 10 completed cards with 2 escalations. The /metrics endpoint returns
    HTTP 200 with sprint_escalation_rate_percent 20."""
    url = _start_scrape_server(tmp_path, [COMPLETED_CARD] * 10, escalations=2)
    status, body = _fetch(url)

    assert status == 200
    assert "sprint_escalation_rate_percent 20" in body


def test_scrape_reports_zero_for_empty_cards_file(tmp_path):
    """AC5: an empty cards file. The /metrics endpoint returns HTTP 200 with all
    six metric lines at 0."""
    url = _start_scrape_server(tmp_path, [])
    status, body = _fetch(url)

    assert status == 200
    assert "sprint_cycle_time_days 0" in body
    assert "sprint_lead_time_days 0" in body
    assert "sprint_throughput_cards 0" in body
    assert "sprint_wip_violations 0" in body
    assert "sprint_blocked_aging_days 0" in body
    assert "sprint_escalation_rate_percent 0" in body
