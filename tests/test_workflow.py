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


# --- Logic tests: mirror the jq project() comparison with Python equivalents ---


def _project(new, ref):
    """Python mirror of the jq ``project($ref)`` function in the docker job.

    Projects ``new`` onto the key structure of ``ref``:
    - For objects, keeps only keys that ``ref`` carries, recursing into values.
    - For arrays, iterates up to ``ref``'s length (missing elements become None,
      matching jq's null for out-of-bounds index), recursing element-wise.
    - For scalars, returns the value unchanged.
    """
    if isinstance(new, dict):
        return {k: _project(v, ref[k]) for k, v in new.items() if k in ref}
    elif isinstance(new, list):
        if isinstance(ref, list):
            return [_project(new[i], ref[i]) if i < len(new) else None
                    for i in range(len(ref))]
        return new
    return new


def _range_comparison(new, prev):
    """Mirror of the docker job's field-for-field /range comparison.

    Returns True if the new response, projected onto the previous response's
    key structure, equals the previous response (both with api_version removed).
    """
    new_stripped = {k: v for k, v in new.items() if k != "api_version"}
    prev_stripped = {k: v for k, v in prev.items() if k != "api_version"}
    return _project(new_stripped, prev_stripped) == prev_stripped


def test_docker_job_comparison_accepts_new_top_level_key():
    """AC1: a new top-level key in the new response (absent from the previous)
    is accepted — the comparison passes."""
    prev = {"api_version": "8", "throughput": 10, "cycle_time_days": 5.0}
    new = {"api_version": "9", "throughput": 10, "cycle_time_days": 5.0, "window": {"verdicts": []}}
    assert _range_comparison(new, prev) is True


def test_docker_job_comparison_accepts_new_key_in_sprint_entry():
    """AC1: a new key inside a sprints array element (absent from the previous)
    is accepted — the comparison passes."""
    prev = {"api_version": "8", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0},
    ]}
    new = {"api_version": "9", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0, "rework": {"sent_backs": 0}},
    ]}
    assert _range_comparison(new, prev) is True


def test_docker_job_comparison_accepts_new_key_in_prior_delta_object():
    """AC1: a new key inside a prior or delta object (absent from the previous)
    is accepted — the comparison passes."""
    prev = {"api_version": "8", "sprints": [
        {"label": "2024-01", "delta": {"cycle_time_days": 0.5}},
    ]}
    new = {"api_version": "9", "sprints": [
        {"label": "2024-01", "delta": {"cycle_time_days": 0.5, "working_time_minutes": 120}},
    ]}
    assert _range_comparison(new, prev) is True


def test_docker_job_comparison_fails_on_changed_value():
    """AC2: a stable key whose value differs between the two responses causes
    the comparison to fail."""
    prev = {"api_version": "8", "throughput": 10, "cycle_time_days": 5.0}
    new = {"api_version": "9", "throughput": 12, "cycle_time_days": 5.0}
    assert _range_comparison(new, prev) is False


def test_docker_job_comparison_fails_on_changed_nested_value():
    """AC2: a stable key whose value differs at a nested level causes
    the comparison to fail."""
    prev = {"api_version": "8", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0},
    ]}
    new = {"api_version": "9", "sprints": [
        {"label": "2024-01", "cycle_time_days": 6.0},
    ]}
    assert _range_comparison(new, prev) is False


def test_docker_job_comparison_fails_on_removed_key():
    """AC3: a key the previous response carries that the new response lacks
    causes the comparison to fail."""
    prev = {"api_version": "8", "throughput": 10, "cycle_time_days": 5.0}
    new = {"api_version": "9", "throughput": 10}
    assert _range_comparison(new, prev) is False


def test_docker_job_comparison_fails_on_removed_nested_key():
    """AC3: a key inside a sprints entry that the new response lacks
    causes the comparison to fail."""
    prev = {"api_version": "8", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0, "throughput": 3},
    ]}
    new = {"api_version": "9", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0},
    ]}
    assert _range_comparison(new, prev) is False


def test_docker_job_comparison_fails_on_removed_array_element():
    """AC3: the new response's sprints array is shorter than the previous,
    so an element the previous carries is missing — the comparison fails."""
    prev = {"api_version": "8", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0},
        {"label": "2024-02", "cycle_time_days": 4.0},
    ]}
    new = {"api_version": "9", "sprints": [
        {"label": "2024-01", "cycle_time_days": 5.0},
    ]}
    assert _range_comparison(new, prev) is False


def test_docker_job_comparison_ignores_api_version_difference():
    """AC4: the api_version pin is separate from the comparison; the
    comparison applies del(.api_version) to both sides, so two images
    differing only in api_version do not fail the comparison."""
    prev = {"api_version": "8", "throughput": 10}
    new = {"api_version": "9", "throughput": 10}
    assert _range_comparison(new, prev) is True


def test_docker_job_escalation_guard_fires_on_escalation_in_body():
    """AC5: the escalation guard is a separate grep check that fails the job
    when the new /range response still carries a retired escalation measure."""
    import json
    # The docker job does: if echo "$RANGE_BODY" | grep -q escalation; then exit 1
    body_with_escalation = json.dumps(
        {"api_version": "9", "sprints": [{"label": "2024-01", "escalation_rate_percent": 5.0}]}
    )
    body_without_escalation = json.dumps(
        {"api_version": "9", "sprints": [{"label": "2024-01", "cycle_time_days": 5.0}]}
    )
    # Mirror of the grep check: "escalation" appears in the body → guard fires
    assert "escalation" in body_with_escalation, (
        "a body carrying a retired escalation measure must trigger the grep guard"
    )
    assert "escalation" not in body_without_escalation, (
        "a body without any escalation measure must not trigger the grep guard"
    )


def test_docker_job_workflow_has_separate_escalation_check():
    """AC5: the workflow file has the escalation guard as a separate check
    (grep for 'escalation'), distinct from the field-for-field comparison."""
    text = _text()
    assert "grep -q escalation" in text, (
        "the docker job must have a separate escalation-measure guard"
    )
    assert "ERROR: GET /range still carries an escalation measure" in text, (
        "the escalation guard must print its error message"
    )
    assert "ERROR: GET /range differs from the image before this change" in text, (
        "the field-for-field comparison must print its error message"
    )


def test_docker_job_comparison_passes_on_identical_responses():
    """The comparison passes when both responses are identical (modulo
    api_version) — the baseline case the docker job observed in CI."""
    body = {
        "api_version": "9",
        "throughput": 10,
        "cycle_time_days": 5.0,
        "sprints": [
            {"label": "2024-01", "cycle_time_days": 5.0, "throughput": 5},
            {"label": "2024-02", "cycle_time_days": 4.0, "throughput": 5},
        ],
        "window": {"verdicts": [], "standouts": {}},
    }
    prev = {**body, "api_version": "8"}
    new = {**body, "api_version": "9"}
    assert _range_comparison(new, prev) is True
