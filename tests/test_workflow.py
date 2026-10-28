"""Tests for the CI docker job's /range comparison in .github/workflows/tests.yml.

The docker job is the project's field-for-field check that a release's image still
answers /range the way the previous main's image did. The comparison is derived
from the previous response's key structure: every key the previous response carries
must have the same value in the new response, while new keys are accepted without
a per-release edit of a deletion list. The job's api_version pin must track the
version in force rather than a constant assumed to hold across the Goal.
"""

import re
from pathlib import Path

from sprint_metrics.report import API_VERSION

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "tests.yml"


def _text() -> str:
    return WORKFLOW.read_text()


def test_docker_job_range_filter_accounts_for_rework_key():
    """The field-for-field /range comparison is derived from the previous
    response's key structure, not a hand-edited deletion list: a new key
    (like rework) is accepted without a per-release edit of the list."""
    text = _text()
    assert "RANGE_FILTER" not in text, (
        "the docker job's /range comparison must not reference a hand-edited deletion list"
    )
    assert "def project" in text, (
        "the docker job's /range comparison must derive the acceptable keys from the previous response"
    )


def test_docker_job_range_filter_accounts_for_window_key():
    """The field-for-field /range comparison handles top-level keys by
    projecting the new response onto the previous response's key set,
    so a new top-level key (like window) is accepted without a deletion entry."""
    text = _text()
    assert "with_entries" in text, (
        "the docker job's /range comparison must project object keys from the previous response"
    )
    assert "has($k)" in text, (
        "the docker job's /range comparison must select only keys the previous response carries"
    )


def test_docker_job_range_filter_accounts_for_window_verdicts():
    """The field-for-field /range comparison is recursive: nested keys
    (like window.verdicts) are handled by the same projection at every level,
    so no per-key entry is needed for deeply nested additions."""
    text = _text()
    assert "project($ref[$k])" in text, (
        "the docker job's /range comparison must recurse into nested objects"
    )


def test_docker_job_range_filter_accounts_for_working_time_key():
    """The field-for-field /range comparison handles array elements
    (like per-sprint working_time) by iterating the previous response's
    array length, so new per-sprint keys need no deletion entry."""
    text = _text()
    assert "range(0; $ref | length)" in text, (
        "the docker job's /range comparison must iterate array elements by the previous response's length"
    )


def test_docker_job_api_version_pin_matches_response_api_version():
    """AC9: every api_version pin in the docker job equals the response
    api_version in force (report.API_VERSION); the pin is not an assumed '4'."""
    pins = re.findall(r'api_version == "(.*?)"', _text())
    assert pins, "no api_version pin found in the docker job"
    for pin in pins:
        assert pin == API_VERSION, f"docker job pins api_version {pin!r}, but the response is {API_VERSION!r}"
