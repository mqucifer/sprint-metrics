"""Tests for the CI docker job's /range comparison in .github/workflows/tests.yml.

The docker job is the project's field-for-field check that a release's image still
answers /range the way the previous main's image did, modulo the changes the story
declares. The story's change (a new per-sprint ``rework`` key) must be accounted
for in that comparison, and the job's api_version pin must track the version in
force rather than a constant assumed to hold across the Goal.
"""

import re
from pathlib import Path

from sprint_metrics.report import API_VERSION

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "tests.yml"


def _text() -> str:
    return WORKFLOW.read_text()


def test_docker_job_range_filter_accounts_for_rework_key():
    """AC9: the field-for-field /range comparison filters out the new rework key,
    the way it already filters out the removed escalation measures."""
    text = _text()
    filter_block = text.split("RANGE_FILTER='", 1)[1].split("'", 1)[0]
    assert ".rework" in filter_block, (
        "the docker job's /range comparison must account for the new rework key"
    )


def test_docker_job_api_version_pin_matches_response_api_version():
    """AC9: every api_version pin in the docker job equals the response
    api_version in force (report.API_VERSION); the pin is not an assumed '4'."""
    pins = re.findall(r'api_version == "(.*?)"', _text())
    assert pins, "no api_version pin found in the docker job"
    for pin in pins:
        assert pin == API_VERSION, f"docker job pins api_version {pin!r}, but the response is {API_VERSION!r}"
