"""Tests for the CI docker job's /range comparison in .github/workflows/tests.yml.

The docker job is the project's field-for-field check that this change's image still
answers /range the way the previous main's image did. Every answer must keep its
value, and nothing may be added or removed, apart from what `declared-changes.json`
declares: each answer a change adds, changes or removes on purpose, by its JSONPath
(RFC 9535). The release empties the declaration and moves api_version once, so a
declared change is accepted for that release only, never for good
(mqucifer/crew#1019). The comparison is the job's script,
.github/scripts/compare_range.py, run here as the job runs it.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sprint_metrics.report import API_VERSION

ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
SCRIPT = ROOT / ".github" / "scripts" / "compare_range.py"
DECLARATION = ROOT / "declared-changes.json"

WORKING_TIME = {
    "response": "GET /range",
    "path": "$.sprints[*].working_time",
    "why": "working time counts session minutes (mqucifer/sprint-metrics#938)",
}


def _text() -> str:
    return WORKFLOW.read_text()


def _run(tmp_path, prev, new, declared):
    """Run the job's script on two /range bodies and a declaration, as the job does."""
    files = []
    for name, body in (("previous", prev), ("new", new), ("declared", declared)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(body))
        files.append(str(path))
    return subprocess.run([sys.executable, str(SCRIPT), *files], capture_output=True, text=True)


def _compare(tmp_path, prev, new, changes=(), api_version="9"):
    return _run(tmp_path, prev, new, {"api_version": api_version, "changes": list(changes)})


# --- the job runs the script on the declaration --------------------------------------


def test_the_docker_job_compares_range_by_the_declaration():
    text = _text()
    assert "python3 .github/scripts/compare_range.py" in text
    assert "declared-changes.json" in text


def test_the_docker_job_keeps_no_answer_out_of_the_comparison_for_good():
    """mqucifer/sprint-metrics#971 passed by deleting working_time from both sides, and
    the deletion merged, so a later regression in working time wasn't caught."""
    text = _text()
    assert "del(" not in text
    assert "working_time" not in text
    assert 'api_version == "' not in text, "the job reads the version from the declaration"


def test_the_declaration_is_the_response_api_version_in_force():
    declared = json.loads(DECLARATION.read_text())
    assert declared["api_version"] == API_VERSION
    assert isinstance(declared["changes"], list)


# --- an undeclared change fails, a declared one passes --------------------------------


def test_identical_responses_pass(tmp_path):
    body = {
        "api_version": "9",
        "throughput": 10,
        "sprints": [
            {"label": "2024-01", "cycle_time_days": 5.0, "throughput": 5},
            {"label": "2024-02", "cycle_time_days": 4.0, "throughput": 5},
        ],
        "window": {"verdicts": [], "standouts": {}},
    }
    ran = _compare(tmp_path, {**body, "api_version": "8"}, body)
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_an_undeclared_changed_value_fails_naming_it(tmp_path):
    prev = {"api_version": "9", "sprints": [{"label": "2024-01", "working_time": {"total": 72}}]}
    new = {"api_version": "9", "sprints": [{"label": "2024-01", "working_time": {"total": 22}}]}
    ran = _compare(tmp_path, prev, new)
    assert ran.returncode == 1
    assert "ERROR: GET /range differs from the image before this change" in ran.stdout
    assert "$.sprints[0].working_time.total" in ran.stdout
    assert '"$.sprints[*].working_time.total"' in ran.stdout, "it says what to declare"


def test_a_declared_changed_value_passes(tmp_path):
    prev = {"api_version": "9", "sprints": [{"label": "a", "working_time": {"total": 72}}] * 2}
    new = {"api_version": "9", "sprints": [{"label": "a", "working_time": {"total": 22}}] * 2}
    ran = _compare(tmp_path, prev, new, [WORKING_TIME])
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "$.sprints[*].working_time" in ran.stdout, "it says what it accepted"


def test_a_declared_change_accepts_only_what_it_names(tmp_path):
    prev = {"api_version": "9", "sprints": [{"working_time": 72, "idle": 10}]}
    new = {"api_version": "9", "sprints": [{"working_time": 22, "idle": 60}]}
    ran = _compare(tmp_path, prev, new, [WORKING_TIME])
    assert ran.returncode == 1
    found = ran.stdout.split("ERROR")[1]
    assert "$.sprints[0].idle" in found
    assert "working_time" not in found


def test_a_change_declared_for_another_response_isn_t_this_one_s(tmp_path):
    prev = {"api_version": "9", "sprints": [{"working_time": 72}]}
    new = {"api_version": "9", "sprints": [{"working_time": 22}]}
    ran = _compare(tmp_path, prev, new, [{**WORKING_TIME, "response": "GET /trend"}])
    assert ran.returncode == 1


def test_a_changed_top_level_value_fails(tmp_path):
    prev, new = {"api_version": "9", "throughput": 10}, {"api_version": "9", "throughput": 12}
    ran = _compare(tmp_path, prev, new)
    assert ran.returncode == 1
    assert "$.throughput" in ran.stdout


def test_an_undeclared_added_answer_fails_and_a_declared_one_passes(tmp_path):
    """An added answer changes what the responses offer, so the release must know of it
    to move api_version: it's declared like any other change."""
    prev = {"api_version": "9", "sprints": [{"label": "2024-01"}]}
    new = {"api_version": "9", "sprints": [{"label": "2024-01", "rework": {"sent_backs": 0}}]}
    ran = _compare(tmp_path, prev, new)
    assert ran.returncode == 1
    assert "added" in ran.stdout and "$.sprints[0].rework" in ran.stdout
    rework = {"response": "GET /range", "path": "$.sprints[*].rework", "why": "new answer"}
    assert _compare(tmp_path, prev, new, [rework]).returncode == 0


def test_an_undeclared_removed_answer_fails_and_a_declared_one_passes(tmp_path):
    prev = {"api_version": "9", "sprints": [{"label": "2024-01", "throughput": 3}]}
    new = {"api_version": "9", "sprints": [{"label": "2024-01"}]}
    ran = _compare(tmp_path, prev, new)
    assert ran.returncode == 1
    assert "removed" in ran.stdout and "$.sprints[0].throughput" in ran.stdout
    gone = {"response": "GET /range", "path": "$.sprints[*].throughput", "why": "retired"}
    assert _compare(tmp_path, prev, new, [gone]).returncode == 0


def test_a_shorter_array_fails(tmp_path):
    prev = {"api_version": "9", "sprints": [{"label": "2024-01"}, {"label": "2024-02"}]}
    new = {"api_version": "9", "sprints": [{"label": "2024-01"}]}
    ran = _compare(tmp_path, prev, new)
    assert ran.returncode == 1
    assert "$.sprints[1]" in ran.stdout


def test_a_numbered_path_names_one_element(tmp_path):
    prev = {"api_version": "9", "sprints": [{"working_time": 1}, {"working_time": 2}]}
    new = {"api_version": "9", "sprints": [{"working_time": 5}, {"working_time": 6}]}
    first = {**WORKING_TIME, "path": "$.sprints[0].working_time"}
    ran = _compare(tmp_path, prev, new, [first])
    assert ran.returncode == 1
    found = ran.stdout.split("ERROR")[1]
    assert "$.sprints[1].working_time" in found
    assert "$.sprints[0].working_time" not in found


def test_a_wildcard_reaches_every_sprint_keyed_by_its_label(tmp_path):
    """/range keys its sprints by label, an object, and RFC 9535's [*] selects an
    object's members as it does an array's elements. The labels aren't names a dot
    can follow, so a difference names them in brackets."""
    prev = {"api_version": "9", "sprints": {"2024-01": {"working_time": {"total": 72}, "idle": 1}}}
    new = {"api_version": "9", "sprints": {"2024-01": {"working_time": {"total": 22}, "idle": 2}}}
    ran = _compare(tmp_path, prev, new, [WORKING_TIME])
    assert ran.returncode == 1
    found = ran.stdout.split("ERROR")[1]
    assert "$.sprints['2024-01'].idle" in found
    assert "working_time" not in found
    idle = {"response": "GET /range", "path": "$.sprints['2024-01'].idle", "why": "x"}
    assert _compare(tmp_path, prev, new, [WORKING_TIME, idle]).returncode == 0


# --- the api_version -------------------------------------------------------------------


def test_the_api_version_is_left_out_of_the_comparison(tmp_path):
    prev, new = {"api_version": "8", "throughput": 10}, {"api_version": "9", "throughput": 10}
    ran = _compare(tmp_path, prev, new)
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_the_response_carries_the_declared_api_version(tmp_path):
    body = {"api_version": "10", "throughput": 10}
    ran = _compare(tmp_path, body, body, api_version="9")
    assert ran.returncode == 1
    assert 'api_version "10"' in ran.stdout and '"9"' in ran.stdout


# --- a declaration it can't read fails, saying why ------------------------------------


@pytest.mark.parametrize(
    "path", ["sprints[*].working_time", "$..working_time", "$.sprints[?@.x]", "$.sprints[0:2]", "$"]
)
def test_a_path_outside_the_subset_it_reads_fails(tmp_path, path):
    body = {"api_version": "9", "sprints": []}
    ran = _compare(tmp_path, body, body, [{**WORKING_TIME, "path": path}])
    assert ran.returncode == 1
    assert "declared-changes.json" in ran.stdout and path in ran.stdout


@pytest.mark.parametrize(
    "declared",
    [
        {"api_version": "9", "changes": [{"response": "GET /range", "path": "$.sprints"}]},
        {"api_version": "9", "changes": ["$.sprints"]},
        {"api_version": "9", "changes": {}},
        {"changes": []},
    ],
)
def test_a_declaration_without_its_fields_fails(tmp_path, declared):
    body = {"api_version": "9", "sprints": []}
    ran = _run(tmp_path, body, body, declared)
    assert ran.returncode == 1
    assert "declared-changes.json" in ran.stdout


# --- the retired escalation measures stay a separate check ------------------------------


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


def test_docker_job_escalation_guard_fires_on_escalation_in_body():
    """AC5: the escalation guard is a separate grep check that fails the job
    when the new /range response still carries a retired escalation measure."""
    body_with_escalation = json.dumps(
        {"api_version": "9", "sprints": [{"label": "2024-01", "escalation_rate_percent": 5.0}]}
    )
    body_without_escalation = json.dumps(
        {"api_version": "9", "sprints": [{"label": "2024-01", "cycle_time_days": 5.0}]}
    )
    assert "escalation" in body_with_escalation
    assert "escalation" not in body_without_escalation
