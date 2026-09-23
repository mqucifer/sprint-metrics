"""Tests for the scrape endpoint that serves current sprint metrics."""

import json
import re
import subprocess
import sys
import urllib.request

import pytest

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
IN_FLIGHT_CARD = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}


@pytest.fixture
def start_scrape(tmp_path):
    """Start the command in scrape mode on an ephemeral port and return the /metrics URL.

    The process is terminated when the test finishes, so no server outlives its test.
    """
    processes = []

    def start(cards_path, wip_limits=None, escalations=0):
        argv = [sys.executable, "-m", "sprint_metrics", str(cards_path), "--scrape"]
        argv += ["--port", "0"]
        if wip_limits is not None:
            limits_path = tmp_path / "wip-limits.json"
            limits_path.write_text(json.dumps(wip_limits))
            argv += ["--wip-limits", str(limits_path)]
        if escalations:
            argv += ["--escalations", str(escalations)]

        process = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
        processes.append(process)
        banner = process.stdout.readline()
        match = re.search(r"http://127\.0\.0\.1:\d+/metrics", banner)
        assert match, f"scrape server did not report its URL: {banner!r}"
        return match.group(0)

    yield start

    for process in processes:
        process.terminate()
        process.wait(timeout=5)
        process.stdout.close()


def _write_cards(tmp_path, cards):
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    return cards_path


def _fetch(url):
    """Fetch a URL and return (status_code, body)."""
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode()


def test_scrape_serves_cycle_time_lead_time_throughput_wip_blocked_escalation(
    tmp_path, start_scrape
):
    """AC1: one completed card created 6 days before completion and started 4 days
    before completion, no WIP limits, no escalations. The /metrics endpoint returns
    HTTP 200 with all six metric lines at the expected values."""
    url = start_scrape(_write_cards(tmp_path, [COMPLETED_CARD]))
    status, body = _fetch(url)

    assert status == 200
    lines = body.splitlines()
    assert "sprint_cycle_time_days 4" in lines
    assert "sprint_lead_time_days 6" in lines
    assert "sprint_throughput_cards 1" in lines
    assert "sprint_wip_violations 0" in lines
    assert "sprint_blocked_aging_days 0" in lines
    assert "sprint_escalation_rate_percent 0" in lines


def test_scrape_reflects_updated_cards_file(tmp_path, start_scrape):
    """AC2: the scrape endpoint is running with one completed card. The cards file
    is updated to contain two completed cards. The next /metrics request returns
    HTTP 200 with sprint_throughput_cards 2."""
    cards_path = _write_cards(tmp_path, [COMPLETED_CARD])
    url = start_scrape(cards_path)

    status, body = _fetch(url)
    assert status == 200
    assert "sprint_throughput_cards 1" in body.splitlines()

    cards_path.write_text(json.dumps([COMPLETED_CARD, COMPLETED_CARD]))

    status, body = _fetch(url)
    assert status == 200
    assert "sprint_throughput_cards 2" in body.splitlines()


def test_scrape_reports_wip_violation(tmp_path, start_scrape):
    """AC3: four in-flight cards with a WIP limit of 3 for In Progress. The
    /metrics endpoint returns HTTP 200 with sprint_wip_violations 1."""
    url = start_scrape(_write_cards(tmp_path, [IN_FLIGHT_CARD] * 4), wip_limits={"In Progress": 3})
    status, body = _fetch(url)

    assert status == 200
    assert "sprint_wip_violations 1" in body.splitlines()


def test_scrape_reports_escalation_rate(tmp_path, start_scrape):
    """AC4: 10 completed cards with 2 escalations. The /metrics endpoint returns
    HTTP 200 with sprint_escalation_rate_percent 20."""
    url = start_scrape(_write_cards(tmp_path, [COMPLETED_CARD] * 10), escalations=2)
    status, body = _fetch(url)

    assert status == 200
    assert "sprint_escalation_rate_percent 20" in body.splitlines()


def test_scrape_reports_zero_for_empty_cards_file(tmp_path, start_scrape):
    """AC5: an empty cards file. The /metrics endpoint returns HTTP 200 with all
    six metric lines at 0."""
    url = start_scrape(_write_cards(tmp_path, []))
    status, body = _fetch(url)

    assert status == 200
    lines = body.splitlines()
    assert "sprint_cycle_time_days 0" in lines
    assert "sprint_lead_time_days 0" in lines
    assert "sprint_throughput_cards 0" in lines
    assert "sprint_wip_violations 0" in lines
    assert "sprint_blocked_aging_days 0" in lines
    assert "sprint_escalation_rate_percent 0" in lines
