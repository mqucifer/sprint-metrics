"""Tests for the docs/ files structure and content."""

import re
from pathlib import Path

import pytest

from sprint_metrics._docs_gen import _generate_section_content
from sprint_metrics.thresholds import DEFAULT_THRESHOLDS

DOCS_DIR = Path(__file__).parent.parent / "docs"
README = Path(__file__).parent.parent / "README.md"

ALL_DOCS = [
    "metrics.md",
    "thresholds.md",
    "service.md",
]

REMOVED_DOCS = [
    "usage.md",
    "cards.md",
    "formats.md",
    "scrape.md",
]

MARKER_IDS: dict[str, list[str]] = {
    "metrics.md": ["metrics"],
    "thresholds.md": ["thresholds"],
    "service.md": ["service"],
}

DRIFT_FILES = [(f, m) for f in ALL_DOCS for m in MARKER_IDS[f]]


def _extract_marked_section(text: str, marker_id: str) -> str:
    """Extract the text between BEGIN:marker_id and END:marker_id."""
    pattern = rf"^BEGIN:{re.escape(marker_id)}\n(.*?)^END:{re.escape(marker_id)}\n"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"no BEGIN:{marker_id}/END:{marker_id} pair found"
    return match.group(1)


def test_all_docs_files_exist_with_markers():
    """AC1: the three surviving docs/ files are non-empty, contain a BEGIN/END marker
    pair with a matching identifier, and the content between the markers is non-empty;
    the four removed pages are absent."""
    for filename in ALL_DOCS:
        path = DOCS_DIR / filename
        assert path.exists(), f"docs/{filename} does not exist"
        text = path.read_text()
        assert text.strip(), f"docs/{filename} is empty"
        for marker_id in MARKER_IDS[filename]:
            begin = f"BEGIN:{marker_id}"
            end = f"END:{marker_id}"
            assert begin in text, f"docs/{filename} missing {begin}"
            assert end in text, f"docs/{filename} missing {end}"
            section = _extract_marked_section(text, marker_id)
            assert section.strip(), f"docs/{filename} marked section {marker_id!r} is empty"
    for filename in REMOVED_DOCS:
        path = DOCS_DIR / filename
        assert not path.exists(), f"docs/{filename} should have been removed"


def test_thresholds_md_contains_all_defaults_with_direction():
    """AC3: docs/thresholds.md marked section contains every key-value pair from
    DEFAULT_THRESHOLDS and states the breach direction matching calculate_flags."""
    path = DOCS_DIR / "thresholds.md"
    text = path.read_text()
    section = _extract_marked_section(text, "thresholds")
    lines = section.splitlines()

    for metric, value in DEFAULT_THRESHOLDS.items():
        matching_lines = [line for line in lines if metric in line]
        assert matching_lines, f"docs/thresholds.md missing metric {metric!r}"
        line = matching_lines[0]
        assert str(value) in line, f"docs/thresholds.md line for {metric!r} missing value {value}"
        if metric in ("throughput", "first_attempt_rate_percent"):
            assert "falls below" in line, f"docs/thresholds.md {metric!r} should say 'falls below'"
        else:
            assert "exceeds" in line, f"docs/thresholds.md {metric!r} should say 'exceeds'"


def _check_no_drift(path: Path, marker_id: str, rel_path: str) -> None:
    """Assert the marked section in the file matches what _docs_gen would produce."""
    text = path.read_text()
    section = _extract_marked_section(text, marker_id)
    if not section.strip():
        raise AssertionError(f"{rel_path}: marked section is empty")
    expected = _generate_section_content(marker_id)
    assert section == expected, (
        f"{rel_path}: marked section has drifted from generated content. "
        f"Run `uv run python -m sprint_metrics._docs_gen` to regenerate."
    )


@pytest.mark.parametrize("filename,marker_id", DRIFT_FILES)
def test_drift_check(filename: str, marker_id: str):
    """AC1: each docs/ file's marked section matches the content that
    _docs_gen would generate from the current source code."""
    _check_no_drift(DOCS_DIR / filename, marker_id, f"docs/{filename}")


def test_drift_check_detects_stale_docstring():
    """AC2: when a calculate_* docstring changes and the doc is not regenerated,
    the drift check for docs/metrics.md fails with 'docs/metrics.md' in the message."""
    import sprint_metrics.metrics as metrics_mod

    original_doc = metrics_mod.calculate_cycle_time_and_lead_time.__doc__
    try:
        metrics_mod.calculate_cycle_time_and_lead_time.__doc__ = (
            "Return the sprint's average cycle time and lead time, in whole days. "
            "An additional sentence has been added."
        )
        with pytest.raises(AssertionError, match="docs/metrics.md"):
            _check_no_drift(DOCS_DIR / "metrics.md", "metrics", "docs/metrics.md")
    finally:
        metrics_mod.calculate_cycle_time_and_lead_time.__doc__ = original_doc


def test_drift_check_detects_empty_section(tmp_path):
    """AC3: when a docs file's marked section is empty (markers adjacent), the
    drift check fails naming the file and indicating the marked section is empty."""
    doc_path = tmp_path / "test_doc.md"
    doc_path.write_text("Intro text\nBEGIN:metrics\nEND:metrics\nOutro text\n")
    with pytest.raises(AssertionError, match=r"test_doc\.md.*marked section is empty"):
        _check_no_drift(doc_path, "metrics", "test_doc.md")


def _readme_section(text: str, heading: str) -> str:
    """Return the body of a level-2 section in README.md, up to the next level-2 heading or EOF."""
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"README.md has no section '## {heading}'"
    return match.group(1)


def test_installation_states_python_312_and_no_third_party_packages():
    """AC (updated): the README's git-dependency installation section states Python 3.12 is
    required and names the three third-party runtime packages the tool depends on."""
    text = README.read_text()
    section = _readme_section(text, "Installation")
    assert "3.12" in section
    assert "psycopg" in section
    assert "opentelemetry-sdk" in section
    assert "opentelemetry-exporter-otlp" in section


def test_metrics_md_first_attempt_rate_states_review_qa_semantics():
    """AC8: docs/metrics.md's 'First attempt rate' subsection states that an attempt
    is a hand of the story to review or QA and that the crew's own checks before
    review do not count as attempts."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section_start = text.index("### First attempt rate")
    section_end = text.index("###", section_start + 1)
    section = text[section_start:section_end]
    assert "hand of the story to review or QA" in section
    assert "crew's own checks" in section
    assert "do not count as attempts" in section


def test_metrics_contains_the_original_display_names():
    """AC (migrated): docs/metrics.md contains the original metric display names
    that survive; the escalation rate is gone (#776)."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    section_lower = section.lower()
    for name in (
        "cycle time",
        "lead time",
        "throughput",
        "wip violations",
        "blocked aging",
    ):
        assert name in section_lower, f"missing metric name {name!r} in docs/metrics.md"
    assert "escalation" not in section_lower


def test_metrics_reference_completed_cards_for_exclusion():
    """AC (migrated): docs/metrics.md's metric descriptions reference completed cards,
    conveying that in-flight cards are excluded from the metrics."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    assert "completed" in section.lower()


def test_cycle_time_entry_has_display_name_and_key():
    """AC (migrated): docs/metrics.md's cycle time entry lists the display name
    and metric key, and mentions whole days."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    assert "Cycle time" in section
    assert "cycle_time_days" in section
    assert "whole days" in section.lower()


def test_metrics_list_throughput_lead_time_blocked_aging():
    """AC (migrated): docs/metrics.md lists throughput, lead time and blocked aging,
    each with its display name and metric key, and no escalation row (#776)."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")

    assert "Throughput" in section
    assert "throughput" in section

    assert "Lead time" in section
    assert "lead_time_days" in section

    assert "Blocked aging" in section
    assert "blocked_aging_days" in section

    assert "escalation_rate_percent" not in section
    assert "escalation_count" not in section


def test_wip_violations_entry_has_display_name_and_key():
    """AC (migrated): docs/metrics.md's WIP violations entry lists the display name
    and metric key."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    assert "WIP violations" in section
    assert "wip_violations" in section


def test_installation_shows_uv_pip_install_with_version_tag():
    """AC1 (migrated): the README's installation section contains a uv pip install command
    with the git URL followed by a version tag."""
    text = README.read_text()
    section = _readme_section(text, "Installation")
    assert "uv pip install" in section
    assert "git+https://github.com/mqucifer/sprint-metrics.git@" in section
    match = re.search(r"sprint-metrics\.git@v\d+\.\d+\.\d+", section)
    assert match is not None, "expected a version tag like v0.1.0 after the git URL"


def test_basic_usage_shows_minimal_invocation_and_stdin():
    """AC1 (migrated): the README's basic-usage section shows the service start
    (docker run with SPRINT_METRICS_DB) and contains no cards file or stdin."""
    text = README.read_text()
    section = _readme_section(text, "Basic usage")
    assert "docker run" in section
    assert "SPRINT_METRICS_DB" in section
    assert "ghcr.io/mqucifer/sprint-metrics" in section
    assert "cards.json" not in section
    assert "standard input" not in section.lower()


def test_first_paragraph_includes_first_attempt_rate_and_failure_breakdown():
    """AC1 (migrated): the first paragraph of the README includes 'first-attempt rate'
    and 'failure breakdown'."""
    text = README.read_text()
    lines = text.splitlines()
    title_idx = next(i for i, line in enumerate(lines) if line.startswith("# "))
    start_idx = None
    for j in range(title_idx + 1, len(lines)):
        if lines[j].strip():
            start_idx = j
            break
    assert start_idx is not None, "no content after title in README.md"
    end_idx = start_idx
    while end_idx + 1 < len(lines) and lines[end_idx + 1].strip():
        end_idx += 1
    paragraph = "\n".join(lines[start_idx : end_idx + 1])
    assert "first-attempt rate" in paragraph
    assert "failure breakdown" in paragraph


def test_first_paragraph_names_cycle_time_lead_time_throughput_wip_and_blocked_aging():
    """AC1: the first paragraph of the README names every measure it computes:
    cycle time, lead time, throughput, WIP-limit violations and blocked-card aging,
    and no longer the escalation rate (#777)."""
    text = README.read_text()
    lines = text.splitlines()
    title_idx = next(i for i, line in enumerate(lines) if line.startswith("# "))
    start_idx = None
    for j in range(title_idx + 1, len(lines)):
        if lines[j].strip():
            start_idx = j
            break
    assert start_idx is not None, "no content after title in README.md"
    end_idx = start_idx
    while end_idx + 1 < len(lines) and lines[end_idx + 1].strip():
        end_idx += 1
    paragraph = "\n".join(lines[start_idx : end_idx + 1])
    assert "cycle time" in paragraph
    assert "lead time" in paragraph
    assert "throughput" in paragraph
    assert "WIP-limit violations" in paragraph
    assert "blocked-card aging" in paragraph
    assert "escalation" not in paragraph


def test_readme_trimmed_has_no_removed_sections():
    """AC1 (migrated): README.md does not contain the removed sections or definitions."""
    text = README.read_text()
    assert "the mean (average) of the difference" not in text
    assert "## Input format" not in text
    assert "## Worked example" not in text


def test_readme_has_changelog_pointer_outside_code_blocks():
    """README.md has a line outside fenced code blocks that names CHANGELOG.md
    and tells the reader where to find version-to-version change history."""
    readme = (Path(__file__).parent.parent / "README.md").read_text()
    lines = readme.splitlines()
    in_code_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block and "CHANGELOG.md" in line:
            lower = line.lower()
            assert "changelog" in lower or "change history" in lower
            return
    pytest.fail("No line outside code blocks references CHANGELOG.md with change history context")


def test_readme_states_same_pr_maintenance_rule():
    """README.md hand-written content has a sentence naming both docs/ and
    CHANGELOG.md that states a user-visible change updates them in the same PR."""
    readme = (Path(__file__).parent.parent / "README.md").read_text()
    for line in readme.splitlines():
        if "docs/" in line and "CHANGELOG.md" in line and "same pull request" in line:
            return
    pytest.fail("No line names both docs/ and CHANGELOG.md with the same-pull-request rule")


def test_readme_unchanged_by_docs_gen():
    """Running _docs_gen does not modify the changelog pointer or maintenance rule
    in README.md."""
    import subprocess

    repo_root = Path(__file__).parent.parent
    readme_path = repo_root / "README.md"
    before = readme_path.read_bytes()

    result = subprocess.run(
        ["uv", "run", "python", "-m", "sprint_metrics._docs_gen"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"_docs_gen failed: {result.stderr}"

    after = readme_path.read_bytes()
    assert before == after, "_docs_gen modified README.md"


def test_service_md_has_handwritten_intro():
    """AC1: docs/service.md's hand-written content before BEGIN:service states
    SPRINT_METRICS_DB, shows a docker run command publishing port 8080, and
    names POST /events and GET /range."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    assert "SPRINT_METRICS_DB" in before, "hand-written content does not mention SPRINT_METRICS_DB"
    assert "docker run" in before, "hand-written content does not show a docker run command"
    assert "8080" in before, "docker run command does not publish port 8080"
    assert "POST /events" in before, "hand-written content does not name POST /events"
    assert "GET /range" in before, "hand-written content does not name GET /range"


def test_service_md_generated_section_contains_all_endpoints():
    """AC2: the text between BEGIN:service and END:service in docs/service.md
    lists exactly the service's endpoints, with the /range endpoint laid out per
    measure: one row per concern module's description fragment, in between the
    fixed first and last rows. GET /metrics and GET /sprint are gone."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    section = _extract_marked_section(text, "service")
    lines = section.splitlines()
    rows = [line.split("|") for line in lines if line.startswith("| GET") or line.startswith("| POST")]
    endpoints = [(row[1].strip(), row[2].strip()) for row in rows]
    # The fixed rows at either end of the table.
    assert endpoints[0] == ("POST", "/sprints")
    assert endpoints[1] == ("POST", "/events")
    assert endpoints[-3:] == [
        ("GET", "/trend"),
        ("GET", "/schema/event"),
        ("GET", "/health"),
    ]
    # Everything in between is a per-measure GET /range row: the base row plus
    # one row per concern module's description fragment.
    range_rows = endpoints[2:-3]
    assert len(range_rows) > 1, "expected the /range endpoint laid out per measure"
    assert all(endpoint == ("GET", "/range") for endpoint in range_rows), (
        "rows between POST /events and GET /trend are not all GET /range rows"
    )


def test_service_md_prose_lists_endpoints_and_documents_metrics_410():
    """#764 AC4: the Endpoints prose names exactly the six endpoints, and the
    error-response section documents the 410 answer for GET /metrics."""
    text = (DOCS_DIR / "service.md").read_text()
    before = text.split("BEGIN:service")[0]
    prose = before[before.index("## Endpoints") :].split("\n\n")[1]
    for endpoint in (
        "POST /sprints",
        "POST /events",
        "GET /range",
        "GET /trend",
        "GET /schema/event",
        "GET /health",
    ):
        assert endpoint in prose
    assert "/metrics" not in prose
    assert "Prometheus" not in prose
    errors = before[before.index("### Error responses") :]
    assert "GET /metrics returns HTTP 410" in errors


def test_metrics_md_has_no_prometheus_name_column():
    """#764 AC3: docs/metrics.md's table has display name, metric key and
    description only, and the intro promises no Prometheus names."""
    text = (DOCS_DIR / "metrics.md").read_text()
    assert "Prometheus" not in text
    section = _extract_marked_section(text, "metrics")
    assert section.splitlines()[0] == "| Display name | Metric key | Description |"


def test_drift_check_service_md_detects_manual_edit(tmp_path):
    """AC4: when the content between BEGIN:service and END:service in docs/service.md
    has been manually edited so it no longer matches what _docs_gen would produce,
    the drift check fails with an assertion message containing 'docs/service.md'."""
    original_text = (DOCS_DIR / "service.md").read_text()
    lines = original_text.splitlines(keepends=True)
    begin_idx = next(i for i, line in enumerate(lines) if line.startswith("BEGIN:service"))
    end_idx = next(i for i, line in enumerate(lines) if line.strip() == "END:service")
    stale = (
        "".join(lines[: begin_idx + 1])
        + "manually edited stale content\n"
        + "".join(lines[end_idx:])
    )
    doc_path = tmp_path / "service.md"
    doc_path.write_text(stale)
    with pytest.raises(AssertionError, match="docs/service.md"):
        _check_no_drift(doc_path, "service", "docs/service.md")


def test_service_md_names_all_event_types():
    """AC5: the hand-written content before BEGIN:service in docs/service.md
    contains each of the five accepted event type names."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    for event_type in ("started", "blocked", "unblocked", "finished", "escalated"):
        assert event_type in before, (
            f"hand-written content does not mention event type {event_type!r}"
        )


def test_service_md_startup_failure_and_sprint_rule():
    """AC6: the hand-written content before BEGIN:service in docs/service.md
    contains 'non-zero' in the context of a startup failure, and contains
    'where it finishes' stating the sprint-counting rule."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    assert "non-zero" in before, (
        "hand-written content does not mention non-zero exit on startup failure"
    )
    assert "where it finishes" in before, (
        "hand-written content does not state the sprint-counting rule"
    )


def test_service_md_documents_otel_environment_variables():
    """AC1: OTEL env vars are documented with descriptions and the default service name."""
    path = Path("docs/service.md")
    text = path.read_text()
    begin = text.index("BEGIN:service")
    end = text.index("END:service") + len("END:service")
    handwritten = text[:begin] + text[end:]
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in handwritten
    assert "OTLP receiver URL" in handwritten
    assert "OTEL_SERVICE_NAME" in handwritten
    assert "sprint-metrics" in handwritten


def test_service_md_shows_sample_span_and_log_record():
    """AC2: A sample span and log record are shown in the hand-written Telemetry section."""
    path = Path("docs/service.md")
    text = path.read_text()
    begin = text.index("BEGIN:service")
    end = text.index("END:service") + len("END:service")
    handwritten = text[:begin] + text[end:]
    # Sample span: name, service name, HTTP attribute
    assert "POST /events" in handwritten
    assert "sprint-metrics" in handwritten
    assert "http.method" in handwritten
    # Sample log record: severity and event action in body
    assert "INFO" in handwritten
    assert "started" in handwritten


def test_service_md_telemetry_section_survives_docs_gen(tmp_path):
    """AC3: The hand-written Telemetry section is not modified by the docs generator."""
    from sprint_metrics._docs_gen import generate_file

    src = Path("docs/service.md")
    original = src.read_text()
    dest = tmp_path / "service.md"
    dest.write_text(original)
    generate_file(dest)
    regenerated = dest.read_text()
    orig_telemetry = original[original.index("END:service") :]
    new_telemetry = regenerated[regenerated.index("END:service") :]
    assert orig_telemetry == new_telemetry


def test_service_md_trend_row_describes_response_shape():
    """AC1: the /trend row in docs/service.md's generated section states the response
    is a JSON object with api_version and an ordered sequence of sprint-label-to-value
    pairs, and that minute-based metrics return JSON integers or JSON null."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    section = _extract_marked_section(text, "service")
    trend_rows = [line for line in section.splitlines() if "/trend" in line]
    assert trend_rows, "no /trend row found in generated section"
    row = trend_rows[0]
    assert "JSON object" in row, "trend row does not state the response is a JSON object"
    assert "api_version" in row, "trend row does not name the api_version field"
    assert "ordered sequence of sprint-label-to-value pairs" in row, (
        "trend row does not describe the values as an ordered sequence of sprint-label-to-value pairs"
    )
    assert "cycle_time_minutes" in row, (
        "trend row does not list cycle_time_minutes as a valid metric"
    )
    assert "lead_time_minutes" in row, "trend row does not list lead_time_minutes as a valid metric"
    assert "JSON integer" in row, "trend row does not state minute-based values are JSON integers"
    assert "JSON null" in row, "trend row does not state gap sprints return JSON null"


def test_service_md_trend_row_names_dora_measures_with_units():
    """AC4: the /trend row in docs/service.md's generated section lists DORA's four
    measures among the valid metrics, names their units (releases per sprint,
    whole days, whole percent, whole minutes), and states that a sprint without
    a derivable DORA value returns JSON null."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    section = _extract_marked_section(text, "service")
    trend_rows = [line for line in section.splitlines() if "/trend" in line]
    assert trend_rows, "no /trend row found in generated section"
    row = trend_rows[0]
    for metric in (
        "release_frequency",
        "dora_lead_time_days",
        "change_failure_rate_percent",
        "mean_time_to_recovery_minutes",
    ):
        assert metric in row, f"trend row does not list {metric} as a valid metric"
    assert "releases per sprint" in row, (
        "trend row does not name release frequency's unit as releases per sprint"
    )
    assert "whole days" in row, "trend row does not name DORA lead time's unit as whole days"
    assert "whole percent" in row, (
        "trend row does not name the change-failure rate's unit as whole percent"
    )
    assert "whole minutes" in row, (
        "trend row does not name mean time to recovery's unit as whole minutes"
    )
    assert "without a derivable DORA value" in row and "JSON null" in row, (
        "trend row does not state that a sprint without a derivable DORA value returns JSON null"
    )


def test_service_md_documents_superseded_event():
    """AC1: the hand-written content before BEGIN:service in docs/service.md names
    'superseded' as an accepted event type, describes because accepting 'sponsor'
    and 'story_problem', describes replaced_by as an optional array of story
    identifiers absent when the crew does not know the replacements, and states
    that no prior event on the card is required."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    assert "superseded" in before, (
        "hand-written content does not name 'superseded' as an accepted event type"
    )
    assert "sponsor" in before, "hand-written content does not name 'sponsor' as a because value"
    assert "story_problem" in before, (
        "hand-written content does not name 'story_problem' as a because value"
    )
    assert "replaced_by" in before, "hand-written content does not name 'replaced_by'"
    assert "optional" in before.lower(), (
        "hand-written content does not state replaced_by is optional"
    )
    assert "no prior event" in before.lower(), (
        "hand-written content does not state no prior event is required"
    )


def test_service_md_documents_returned_event():
    """AC6: the hand-written Event intake content in docs/service.md names 'returned'
    as an accepted event type, documents its three fields — failure_role (the step
    the story was sent back from), failure_class (the reason), and epic (the story's
    epic link) — as optional, and states re-sending one is as safe as re-sending any
    other; the generated endpoints table names 'returned' among the accepted types."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    assert "returned" in before, (
        "hand-written content does not name 'returned' as an accepted event type"
    )
    anchor = before.index("A `returned` event")
    returned_text = before[anchor : anchor + 700]
    for field in ("failure_role", "failure_class", "epic"):
        assert field in returned_text, f"returned-event documentation does not name {field!r}"
    assert "optional" in returned_text.lower(), (
        "returned-event documentation does not state the fields are optional"
    )
    assert "re-sending" in returned_text.lower(), (
        "returned-event documentation does not state re-sending is safe"
    )
    section = _extract_marked_section(text, "service")
    events_rows = [line for line in section.splitlines() if "/events" in line]
    assert any("returned" in row for row in events_rows), (
        "generated endpoints table does not name 'returned' among the accepted event types"
    )


def test_service_md_documents_filed_event():
    """AC1: the hand-written Event intake content in docs/service.md names 'filed'
    as an accepted event type, documents filer, opener, and project as the filing
    facts the crew sends (each a fact, not a count, and each optional)."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    assert "filed" in before, (
        "hand-written content does not name 'filed' as an accepted event type"
    )
    anchor = before.index("A `filed` event")
    filed_text = before[anchor : anchor + 1000]
    for field in ("filer", "opener", "project"):
        assert field in filed_text, f"filed-event documentation does not name {field!r}"
    assert "optional" in filed_text.lower(), (
        "filed-event documentation does not state the fields are optional"
    )
    assert "not a count" in filed_text, (
        "filed-event documentation does not state each field is a fact, not a count"
    )


def test_service_md_filed_event_documents_buckets():
    """AC2: the 'filed' documentation names the filer side values (crew, sponsor,
    operator, other) and the opener kinds (found, process, split) with their
    meanings, so the facts the crew sends bucket correctly."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    anchor = before.index("A `filed` event")
    filed_text = before[anchor : anchor + 1200]
    for value in ("crew", "sponsor", "operator", "other"):
        assert f'"{value}"' in filed_text, (
            f"filed-event documentation does not name filer side {value!r}"
        )
    for value in ("found", "process", "split"):
        assert f'"{value}"' in filed_text, (
            f"filed-event documentation does not name opener kind {value!r}"
        )
    assert "found a problem" in filed_text, (
        "filed-event documentation does not explain what 'found' means"
    )
    assert "test, release, review, technical epic, or retro" in filed_text, (
        "filed-event documentation does not explain what 'process' means"
    )
    assert "split from something already filed" in filed_text, (
        "filed-event documentation does not explain what 'split' means"
    )


def test_service_md_filed_event_documents_unknown():
    """AC3: the 'filed' documentation states that a card whose opener cannot be
    told apart is reported as unknown — the opener fact is left out rather than
    guessed — and that the service never infers a bucket from an absent fact."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    anchor = before.index("A `filed` event")
    filed_text = before[anchor : anchor + 1400]
    assert "unknown" in filed_text.lower(), (
        "filed-event documentation does not state the card is reported as unknown"
    )
    assert "left out" in filed_text.lower(), (
        "filed-event documentation does not state the opener fact is left out"
    )
    assert "never infers" in filed_text, (
        "filed-event documentation does not state the service never infers a bucket"
    )
    assert "absent fact" in filed_text, (
        "filed-event documentation does not reference an absent fact"
    )


def test_service_md_filed_event_documents_project_identity():
    """AC4: the 'filed' documentation states that card ids are unique within a
    project and that the project fact distinguishes a card "123" in one repository
    from card "123" in another — the two count as two distinct cards."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    anchor = before.index("A `filed` event")
    filed_text = before[anchor : anchor + 1600]
    assert "unique within a project" in filed_text, (
        "filed-event documentation does not state card ids are unique within a project"
    )
    assert '"123"' in filed_text, (
        "filed-event documentation does not use the card '123' example"
    )
    assert "two distinct cards" in filed_text, (
        "filed-event documentation does not state the two count as two distinct cards"
    )


def test_service_md_filed_example_validates_against_schema():
    """AC5: the 'filed' example event documented in docs/service.md validates
    against the event-intake schema, so drift between the docs and the schema is
    provable on a pull request."""
    import json as json_mod

    import jsonschema

    from sprint_metrics.schema import EVENT_INTAKE_SCHEMA

    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    # Find the filed example JSON block
    example_idx = before.index("Example `filed` event")
    after_example = before[example_idx:]
    json_start = after_example.index("```json")
    json_end = after_example.index("```", json_start + 7)
    json_block = after_example[json_start + 7 : json_end]
    event = json_mod.loads(json_block)
    # The example must be a well-formed 'filed' event the intake accepts.
    jsonschema.validate(event, EVENT_INTAKE_SCHEMA)


def test_service_md_filed_event_states_api_version_stays_one():
    """AC6: the 'filed' documentation states the intake's api_version stays "1"
    (the 'filed' event is additive) and that events without the filing facts are
    accepted exactly as today."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    anchor = before.index("A `filed` event")
    filed_text = before[anchor : anchor + 2000]
    assert 'stays "1"' in filed_text or "stays \"1\"" in filed_text, (
        "filed-event documentation does not state api_version stays '1'"
    )
    assert "additive" in filed_text, (
        "filed-event documentation does not state the 'filed' event is additive"
    )
    assert "exactly as today" in filed_text, (
        "filed-event documentation does not state events without filing facts are accepted as today"
    )


def test_service_md_sprint_range_description_describes_filed():
    """AC5: the /range endpoint description in docs/service.md names the filed
    section's fields — the crew-filed total, its found/from-process/split/unknown
    counts, the Sponsor/operator/other counts, the sprint's total cards and the
    self-filed share with its numerator and denominator — and states that a card
    counts in the sprint it was filed in, not the sprint it merged."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    after_begin = text.split("BEGIN:service", 1)[1]
    anchor = after_begin.index("carries filed")
    filed_row = after_begin[anchor : anchor + 1700]
    for key in (
        "crew_total",
        "found",
        "from_process",
        "split",
        "unknown",
        "sponsor",
        "operator",
        "other",
        "total_cards",
    ):
        assert key in filed_row, f"/range filed description does not name {key!r}"
    assert "self_filed_share" in filed_row, (
        "/range filed description does not name the self-filed share"
    )
    assert "numerator" in filed_row and "denominator" in filed_row, (
        "/range filed description does not carry the share's numerator and denominator"
    )
    assert "the sprint it was filed in" in filed_row, (
        "/range filed description does not state the sprint-attribution rule"
    )
    assert "where it merges" in filed_row, (
        "/range filed description does not state the filed sprint may differ from the merge sprint"
    )


def test_metrics_md_computation_details_describes_filed():
    """AC6: docs/metrics.md's Computation details describes the filed answer — the
    buckets partition the sprint, a sprint with events but no filing facts reads
    null while a true zero (the crew filed nothing) is a distinct answer, and the
    unknown bucket counts in the crew total because those cards were filed but
    can't be told apart."""
    path = DOCS_DIR / "metrics.md"
    text = path.read_text()
    anchor = text.index("### Filed split")
    section = text[anchor : anchor + 2500]
    assert "crew_total = found +" in section, (
        "filed computation details do not state the crew buckets sum to the crew total"
    )
    assert "crew_total + sponsor + operator + other =" in section, (
        "filed computation details do not state the filers sum to the sprint total"
    )
    assert "no stored" in section, (
        "filed computation details do not state a sprint with events but no filing facts reads null"
    )
    assert "crew filed nothing" in section, (
        "filed computation details do not state a true zero (the crew filed nothing) is a distinct answer"
    )
    assert "unknown" in section, (
        "filed computation details do not name the unknown bucket"
    )
    assert "counted in the crew total" in section, (
        "filed computation details do not state the unknown bucket counts in the crew total"
    )


def test_service_md_sprint_range_descriptions_state_per_return_semantics():
    """AC5: the hand-written /range endpoint description in
    docs/service.md states that failure_breakdown and top_failure_causes count
    returns — one entry per return, by (failure class, returning role) — not
    one entry per failed story."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]

    range_start = before.index("GET /range")
    range_section = before[range_start : range_start + 500]

    assert "failure_breakdown" in range_section, (
        "hand-written /range description does not mention failure_breakdown"
    )
    assert "top_failure_causes" in range_section, (
        "hand-written /range description does not mention top_failure_causes"
    )
    assert "one entry per return" in range_section, (
        "hand-written /range description does not state per-return semantics"
    )
    assert "failure class, returning role" in range_section, (
        "hand-written /range description does not name the (class, role) key"
    )


def test_service_md_window_verdict_described_in_handwritten_range_section():
    """AC8: the hand-written /range section in docs/service.md tells the reader
    that the window verdicts compare the window's first and last data-bearing
    sprint, that a measure with a missing number gets no verdict, and what
    "flat" means."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    anchor = before.index("The window object also carries a `verdicts`")
    verdict_section = before[anchor : anchor + 700]
    assert "first and last data-bearing sprint" in verdict_section, (
        "hand-written /range section does not state the verdict compares the "
        "window's first and last data-bearing sprint"
    )
    assert "skipped, not read as zero" in verdict_section, (
        "hand-written /range section does not state a gap sprint is skipped, not read as zero"
    )
    assert "no verdict" in verdict_section, (
        "hand-written /range section does not state a missing number gets no verdict"
    )
    assert '"Flat"' in verdict_section, (
        "hand-written /range section does not define what 'flat' means"
    )


def test_service_md_handwritten_section_survives_docs_gen(tmp_path):
    """AC2: running generate_file on docs/service.md leaves the hand-written
    content before BEGIN:service byte-identical, confirming it resides outside
    the generated markers."""
    from sprint_metrics._docs_gen import generate_file

    src = Path("docs/service.md")
    original = src.read_text()
    dest = tmp_path / "service.md"
    dest.write_text(original)
    generate_file(dest)
    regenerated = dest.read_text()
    orig_handwritten = original[: original.index("BEGIN:service")]
    new_handwritten = regenerated[: regenerated.index("BEGIN:service")]
    assert orig_handwritten == new_handwritten, (
        "hand-written content before BEGIN:service was modified by docs_gen"
    )


def test_service_md_documents_resend_fills_null_fields():
    """AC1: the re-send paragraph states the re-send is safe and that fields
    currently NULL in the stored row receive the value supplied by the re-sent event."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    # The paragraph is a single non-blank line (or group); collect until blank.
    para_lines = [lines[resend_idx]]
    for j in range(resend_idx + 1, len(lines)):
        if lines[j].strip():
            para_lines.append(lines[j])
        else:
            break
    paragraph = " ".join(para_lines)
    assert "safe" in paragraph, "re-send paragraph does not state the re-send is safe"
    assert "NULL" in paragraph, "re-send paragraph does not mention NULL fields"
    assert "receive the value supplied" in paragraph, (
        "re-send paragraph does not state NULL fields receive the supplied value"
    )


def test_service_md_documents_resend_preserves_existing_values():
    """AC2: the re-send paragraph states that a field which already holds a value
    is not changed by the re-sent event."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    para_lines = [lines[resend_idx]]
    for j in range(resend_idx + 1, len(lines)):
        if lines[j].strip():
            para_lines.append(lines[j])
        else:
            break
    paragraph = " ".join(para_lines)
    assert "already hold a value" in paragraph, (
        "re-send paragraph does not state existing values are preserved"
    )
    assert "not changed" in paragraph, (
        "re-send paragraph does not state existing values are not changed"
    )


def test_service_md_resend_paragraph_no_negation_terms():
    """AC3: none of 'discarded', 'ignored', 'skipped', 'DO NOTHING', 'no-op'
    appear in the re-send paragraph."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    para_lines = [lines[resend_idx]]
    for j in range(resend_idx + 1, len(lines)):
        if lines[j].strip():
            para_lines.append(lines[j])
        else:
            break
    paragraph = " ".join(para_lines)
    for term in ("discarded", "ignored", "skipped", "DO NOTHING", "no-op"):
        assert term not in paragraph, f"re-send paragraph contains forbidden term {term!r}"


def test_service_md_resend_paragraph_placement():
    """AC6: the re-send paragraph is preceded by a line beginning 'No prior event
    on the card is required' and followed by a line beginning 'The intake format
    carries'."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    # Find the immediately preceding non-blank line.
    prev_idx = resend_idx - 1
    while prev_idx >= 0 and not lines[prev_idx].strip():
        prev_idx -= 1
    assert prev_idx >= 0, "no preceding line found"
    assert lines[prev_idx].startswith("No prior event on the card is required"), (
        f"preceding line is {lines[prev_idx]!r}, expected to start with "
        "'No prior event on the card is required'"
    )
    # Find the immediately following non-blank line.
    next_idx = resend_idx + 1
    while next_idx < len(lines) and not lines[next_idx].strip():
        next_idx += 1
    assert next_idx < len(lines), "no following line found"
    assert lines[next_idx].startswith("The intake format carries"), (
        f"following line is {lines[next_idx]!r}, expected to start with 'The intake format carries'"
    )


def test_service_md_resend_paragraph_names_identity_fields():
    """AC7: 'card_id', 'type', and 'timestamp' all appear in the re-send paragraph,
    each enclosed in backticks."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    para_lines = [lines[resend_idx]]
    for j in range(resend_idx + 1, len(lines)):
        if lines[j].strip():
            para_lines.append(lines[j])
        else:
            break
    paragraph = " ".join(para_lines)
    for field in ("card_id", "type", "timestamp"):
        assert f"`{field}`" in paragraph, (
            f"re-send paragraph does not contain `{field}` in backticks"
        )


def test_service_md_resend_paragraph_no_implementation_terms():
    """AC8: none of 'COALESCE', 'upsert', 'ON CONFLICT', 'SQL' appear in the
    re-send paragraph."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    para_lines = [lines[resend_idx]]
    for j in range(resend_idx + 1, len(lines)):
        if lines[j].strip():
            para_lines.append(lines[j])
        else:
            break
    paragraph = " ".join(para_lines)
    for term in ("COALESCE", "upsert", "ON CONFLICT", "SQL"):
        assert term not in paragraph, (
            f"re-send paragraph contains forbidden implementation term {term!r}"
        )


def test_service_md_resend_paragraph_starts_at_column_zero():
    """AC9: the re-send paragraph's first line begins at column 0 with the
    character 'R' (the start of 'Re-sending')."""
    path = DOCS_DIR / "service.md"
    text = path.read_text()
    before = text.split("BEGIN:service")[0]
    lines = before.splitlines()
    resend_idx = next(i for i, line in enumerate(lines) if line.startswith("Re-sending"))
    line = lines[resend_idx]
    assert line[0] == "R", f"re-send paragraph first line starts with {line[0]!r}, expected 'R'"


# --- Changelog-rules release-cut docs (epic #692) ---


def _versioning_section() -> str:
    """Extract the README's Versioning section (from '## Versioning' to the next '## ')."""
    text = README.read_text()
    start = text.index("## Versioning")
    rest = text[start + len("## Versioning") :]
    next_heading = rest.find("\n## ")
    if next_heading == -1:
        return rest
    return rest[:next_heading]


def _adr_0011_decision() -> str:
    """Extract the Decision section from the 0011 ADR file."""
    adr_dir = DOCS_DIR / "decisions"
    adr_files = sorted(adr_dir.glob("0011-*.md"))
    assert len(adr_files) == 1, f"Expected one 0011 ADR, found: {adr_files}"
    text = adr_files[0].read_text()
    start = text.index("## Decision")
    rest = text[start + len("## Decision") :]
    next_heading = rest.find("\n## ")
    if next_heading == -1:
        return rest
    return rest[:next_heading]


def test_readme_versioning_states_pyproject_version_rule():
    """AC1: the Versioning section states the version in pyproject.toml equals
    the newest released section's version in CHANGELOG.md."""
    section = _versioning_section()
    assert "pyproject.toml" in section
    assert "newest released section" in section


def test_readme_versioning_states_newest_first_and_date_bound():
    """AC2: the Versioning section states released sections run newest first by
    version, and no released section's date is later than the date of the section
    above it or later than the day the check runs."""
    section = _versioning_section()
    assert "newest first" in section
    assert "later than the day the check runs" in section


def test_readme_versioning_states_unreleased_first_with_subheadings():
    """AC3: the Versioning section states ## [Unreleased] is the first section,
    with the subheadings Added, Changed, Fixed, Removed in that order."""
    section = _versioning_section()
    assert "## [Unreleased]" in section
    assert "Added, Changed, Fixed" in section


def test_readme_versioning_states_released_heading_date_format():
    """AC4: the Versioning section states every released section's heading is
    dated YYYY-MM-DD."""
    section = _versioning_section()
    assert "YYYY-MM-DD" in section


def test_readme_versioning_states_content_not_checked_by_tests():
    """AC5: the Versioning section states a section's content is not checked by tests,
    and entries are checked by review, not by CI."""
    section = _versioning_section()
    assert "not checked by tests" in section
    assert "review, not by CI" in section


def test_adr_0011_decision_states_same_rules_in_order():
    """AC6/AC10: the four rules' markers appear in the same order in both the
    README's Versioning section and ADR 0011's Decision section."""
    readme_section = _versioning_section()
    adr_decision = _adr_0011_decision()

    # Rule 1 marker
    r1_readme = readme_section.index("pyproject.toml")
    r1_adr = adr_decision.index("pyproject.toml")

    # Rule 2 marker
    r2_readme = readme_section.index("newest first")
    r2_adr = adr_decision.index("newest first")

    # Rule 3 marker
    r3_readme = readme_section.index("## [Unreleased]")
    r3_adr = adr_decision.index("## [Unreleased]")

    # Rule 4 marker
    r4_readme = readme_section.index("YYYY-MM-DD")
    r4_adr = adr_decision.index("YYYY-MM-DD")

    # In both files, rule 1 before rule 2 before rule 3 before rule 4
    assert r1_readme < r2_readme < r3_readme < r4_readme
    assert r1_adr < r2_adr < r3_adr < r4_adr


def test_readme_versioning_preserves_semver_and_github_releases():
    """AC11: the Versioning section still contains the SemVer bullets and the
    GitHub Releases sentence."""
    section = _versioning_section()
    assert "SemVer" in section
    assert "MAJOR" in section
    assert "MINOR" in section
    assert "PATCH" in section
    assert "GitHub Releases" in section


def test_adr_0011_file_name_and_heading():
    """AC12: the new ADR file name starts with '0011-' and its H1 heading reads
    '# 11. '."""
    adr_dir = DOCS_DIR / "decisions"
    adr_files = sorted(adr_dir.glob("0011-*.md"))
    assert len(adr_files) == 1, f"Expected one 0011 ADR file, found: {adr_files}"
    first_line = adr_files[0].read_text().splitlines()[0]
    assert first_line.startswith("# 11. ")


def test_adr_0003_status_superseded_by_0011():
    """AC7: 0003's Status line reads 'Superseded by 0011' and its body is
    unedited (Date, Context, Decision, Consequences, Source unchanged)."""
    text = (DOCS_DIR / "decisions" / "0003-releases.md").read_text()
    assert "Superseded by 0011" in text
    assert "**Date:** 2026-09-28" in text
    assert "Releases were cut by hand" in text
    assert "A release is a pull request with the version bump" in text
    assert "The release is reviewed like any change" in text


def test_metrics_md_names_all_cost_measures():
    """AC1: the generated metrics table names every cost measure and the
    computation-details section states model minutes as the display unit."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    for name in (
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
        "cached_input_percent",
        "reasoning_output_percent",
    ):
        assert name in section, f"missing cost measure {name!r} in metrics table"
    assert "Model minutes (middle)" in section
    assert "Model minutes (total)" in section
    # Computation-details states model minutes as display unit
    detail_start = text.index("## Computation details")
    detail = text[detail_start:]
    model_cost_start = detail.index("### Model cost")
    model_cost_section = detail[model_cost_start:]
    assert (
        "display unit" in model_cost_section.lower()
        or "whole minutes" in model_cost_section.lower()
    )
    assert "model_seconds" in model_cost_section
    assert "model_minutes" in model_cost_section


def test_metrics_md_explains_cost_aggregation_semantics():
    """AC2: computation-details explains story cost as summed total across roles,
    middle as median of per-story values, total as sum, and percents from
    the sprint's combined token totals rather than per story."""
    text = (DOCS_DIR / "metrics.md").read_text()
    detail_start = text.index("## Computation details")
    detail = text[detail_start:]
    model_cost_start = detail.index("### Model cost")
    # Find the next section heading (## or ###) after the Model cost heading line
    next_heading = detail.index("\n##", model_cost_start + 1)
    model_cost_section = detail[model_cost_start:next_heading]
    # Story cost is summed total across every role's model calls
    assert (
        "summed total across every role" in model_cost_section
        or "summed total" in model_cost_section
    )
    # Middle is the median of per-story values
    assert "median" in model_cost_section.lower()
    # Total is the sum
    assert "sum" in model_cost_section.lower()
    # Percents from sprint's combined token totals
    assert "combined" in model_cost_section.lower() or "sprint's" in model_cost_section


def test_service_md_documents_cost_payload_fields():
    """AC3: the event-intake section documents the finished event's cost payload
    with all five fields, each a non-negative integer, sent together or not at all."""
    text = (DOCS_DIR / "service.md").read_text()
    before = text.split("BEGIN:service")[0]
    # All five fields are named
    for field in (
        "model_seconds",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    ):
        assert field in before, f"missing cost field {field!r} in event-intake section"
    # States sent together or not at all
    assert "together or not at all" in before or "all-or-nothing" in before
    # States non-negative integer
    assert "non-negative" in before or "minimum 0" in before


def test_service_md_trend_row_lists_cost_metrics():
    """AC4: the generated endpoints table in docs/service.md lists the eight cost
    metric names among the valid /trend metrics."""
    text = (DOCS_DIR / "service.md").read_text()
    section = _extract_marked_section(text, "service")
    for name in (
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
        "cached_input_percent",
        "reasoning_output_percent",
    ):
        assert name in section, f"missing cost metric {name!r} in /trend row"


def test_service_md_trend_row_lists_cost_by_kind_measures():
    """AC5: the /trend row in docs/service.md names the addition_working_time_minutes
    and change_working_time_minutes measures."""
    text = (DOCS_DIR / "service.md").read_text()
    section = _extract_marked_section(text, "service")
    assert "addition_working_time_minutes" in section
    assert "change_working_time_minutes" in section


def test_service_md_trend_row_lists_model_time_split_measures():
    """AC4: the /trend row in docs/service.md names the
    model_time_split_refinement_minutes and model_time_split_delivery_minutes
    measures."""
    text = (DOCS_DIR / "service.md").read_text()
    section = _extract_marked_section(text, "service")
    assert "model_time_split_refinement_minutes" in section
    assert "model_time_split_delivery_minutes" in section


def test_service_md_trend_row_lists_self_filed_share():
    """AC3: the /trend row in docs/service.md names the self_filed_share_percent
    measure among the valid metrics, and states its unit (whole percent) and its
    null rule (null where the sprint carries no filing facts)."""
    text = (DOCS_DIR / "service.md").read_text()
    section = _extract_marked_section(text, "service")
    trend_rows = [line for line in section.splitlines() if "/trend" in line]
    assert trend_rows, "no /trend row found in generated section"
    row = trend_rows[0]
    assert "self_filed_share_percent" in row, (
        "trend row does not list self_filed_share_percent as a valid metric"
    )
    assert "whole percent" in row, "trend row does not state the self-filed share is a whole percent"
    assert "no filing facts" in row, (
        "trend row does not state the self-filed share is null where no filing facts"
    )


def test_service_md_trend_row_documents_self_filed_share_measure():
    """The /trend row documents the self-filed share measure: its unit (a percent
    of the sprint's filed cards, crew-filed count out of the total-filed count,
    unknown cards included in the total), its precision (whole percent), where
    the per-sprint counts behind each value live (the per-sprint filed split in
    the /range answer), its null semantics (no filing facts, not 'no self-filed
    work'), and its zero semantics (the crew filed none)."""
    text = (DOCS_DIR / "service.md").read_text()
    section = _extract_marked_section(text, "service")
    trend_rows = [line for line in section.splitlines() if "/trend" in line]
    assert trend_rows, "no /trend row found in generated section"
    row = trend_rows[0]
    # Precision: whole percent
    assert "whole percent" in row
    # Unit: crew-filed count out of the total-filed count, unknown cards included
    assert "crew-filed count out of the total-filed count" in row
    assert "unknown cards included in the total" in row
    # Where the counts live: the per-sprint filed split in the /range answer
    assert "per-sprint filed split in the /range answer" in row
    # The filed split structure
    assert "of which found" in row
    assert "from its own process" in row
    assert "the Sponsor's" in row
    assert "the operator's" in row
    # Null semantics: no filing facts, not 'no self-filed work'
    assert "no filing facts" in row
    assert "no self-filed work" in row
    # Zero semantics: the crew filed none
    assert "filed none" in row


def test_metrics_md_cost_names_match_service_metrics():
    """AC6: the cost measure names in the generated metrics table match the names
    in ALL_METRICS and _METRIC_COLUMNS exactly."""
    from sprint_metrics.metrics import ALL_METRICS
    from sprint_metrics.report import _METRIC_COLUMNS

    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    cost_metrics = {
        "model_minutes_middle",
        "model_minutes_total",
        "input_tokens_middle",
        "input_tokens_total",
        "output_tokens_middle",
        "output_tokens_total",
        "cached_input_percent",
        "reasoning_output_percent",
    }
    # All cost metrics are in ALL_METRICS
    assert cost_metrics.issubset(ALL_METRICS)
    # All cost metrics have a display name in _METRIC_COLUMNS
    for name in cost_metrics:
        assert name in _METRIC_COLUMNS
        # The display name appears in the generated table
        display = _METRIC_COLUMNS[name]
        assert display in section, f"display name {display!r} not in metrics table"


def test_service_md_range_row_describes_rework_answer():
    """AC10: the GET /range description in docs/service.md tells the reader that
    each sprint's entry carries the stories sent back to the business analyst,
    out of the stories started that sprint, each naming the story, the step it
    was sent back from, and why — and that a send-back counts in the sprint of
    the returned event. The /range rows are laid out per measure, so the rework
    content lives in its own row."""
    section = _extract_marked_section((DOCS_DIR / "service.md").read_text(), "service")
    range_rows = [line for line in section.splitlines() if line.startswith("| GET | /range")]
    row = next(line for line in range_rows if "rework" in line)
    for phrase in (
        "rework",
        "Business Analyst",
        "stories started",
        "identifier",
        "step it was sent back from",
        "reason",
        "sprint of the returned event",
    ):
        assert phrase in row, f"GET /range rework row missing {phrase!r}: {row}"


def test_metrics_md_computation_details_describes_rework_answer():
    """AC10: docs/metrics.md's 'Computation details' tells the reader what the
    rework answer is: the stories sent back to the business analyst, out of the
    stories started that sprint, each naming the story, the step it was sent
    back from, and why — and that a send-back counts in the sprint of the
    returned event."""
    text = (DOCS_DIR / "metrics.md").read_text()
    details = text.split("## Computation details")[1]
    heading = next(
        line for line in details.splitlines() if "Rework" in line and line.startswith("###")
    )
    section = details.split(heading)[1]
    # Stop at the next section or the boundary-conditions heading.
    for stop in ("\n## ", "\n### "):
        if stop in section:
            section = section.split(stop)[0]
    # Markdown wraps long sentences; compare against one-line text.
    import re

    section = re.sub(r"\s+", " ", section)
    for phrase in (
        "rework",
        "Business Analyst",
        "started",
        "step",
        "reason",
        "counts in the sprint of the",
        "`returned`",
        "completes no story",
    ):
        assert phrase in section, f"rework computation details missing {phrase!r}"


def test_metrics_md_describes_working_time_answer():
    """AC5: docs/metrics.md's 'Working time per pipeline step' tells the reader
    that working time per step is the minutes the crew's sessions ran (not the
    creation-to-finish span), that a rework session not re-sent as 'started' is
    invisible to working time (shows as idle), and that a blocked card's blocked
    interval is not counted."""
    text = (DOCS_DIR / "metrics.md").read_text()
    details = text.split("## Computation details")[1]
    heading = next(
        line for line in details.splitlines() if "Working time" in line and line.startswith("###")
    )
    section = details.split(heading)[1]
    for stop in ("\n## ", "\n### "):
        if stop in section:
            section = section.split(stop)[0]
    import re

    section = re.sub(r"\s+", " ", section)
    for phrase in (
        "`working_time`",
        "minutes the crew's sessions ran",
        "not the span",
        "`started`",
        "`finished`, `attempt_failed`, or `returned`",
        "rework session",
        "invisible to working time",
        "idle time",
        "blocked interval",
    ):
        assert phrase in section, f"working time computation details missing {phrase!r}"


def test_metrics_md_working_time_states_step_boundary_pair():
    """AC5: docs/metrics.md's 'Working time per pipeline step' states that a
    'started' row landing immediately before its terminal row is the same step
    boundary and does not open a new zero-minute session that zeros the
    preceding window."""
    text = (DOCS_DIR / "metrics.md").read_text()
    details = text.split("## Computation details")[1]
    heading = next(
        line for line in details.splitlines() if "Working time" in line and line.startswith("###")
    )
    section = details.split(heading)[1]
    for stop in ("\n## ", "\n### "):
        if stop in section:
            section = section.split(stop)[0]
    import re

    section = re.sub(r"\s+", " ", section)
    for phrase in (
        "same step boundary",
        "does not open a new zero-minute session",
        "zeros the preceding window",
    ):
        assert phrase in section, f"step boundary description missing {phrase!r}"


def test_metrics_md_metrics_table_has_working_time_row():
    """AC6: docs/metrics.md's metrics table carries a row for
    working_time_minutes stating what it measures, in whole minutes."""
    text = (DOCS_DIR / "metrics.md").read_text()
    table = _extract_marked_section(text, "metrics")
    row = next(line for line in table.splitlines() if "`working_time_minutes`" in line)
    cells = [c.strip() for c in row.split("|") if c.strip()]
    assert cells[1] == "`working_time_minutes`"
    assert "whole minutes" in row


def test_metrics_md_metrics_table_has_cost_by_kind_rows():
    """AC5: docs/metrics.md's metrics table carries rows for
    addition_working_time_minutes and change_working_time_minutes, stating
    what cost by kind measures, its unit (whole minutes), and that kind-less
    sprints read null."""
    text = (DOCS_DIR / "metrics.md").read_text()
    table = _extract_marked_section(text, "metrics")
    add_row = next(line for line in table.splitlines() if "`addition_working_time_minutes`" in line)
    cells = [c.strip() for c in add_row.split("|") if c.strip()]
    assert cells[1] == "`addition_working_time_minutes`"
    assert "whole minutes" in add_row
    assert "None" in add_row or "null" in add_row.lower()
    chg_row = next(line for line in table.splitlines() if "`change_working_time_minutes`" in line)
    cells = [c.strip() for c in chg_row.split("|") if c.strip()]
    assert cells[1] == "`change_working_time_minutes`"
    assert "whole minutes" in chg_row


def test_metrics_md_metrics_table_has_model_time_split_rows():
    """AC4: docs/metrics.md's metrics table carries rows for
    model_time_split_refinement_minutes and model_time_split_delivery_minutes,
    stating what the split measures (model time, refinement against delivery),
    its unit (whole minutes), and its null behaviour."""
    text = (DOCS_DIR / "metrics.md").read_text()
    table = _extract_marked_section(text, "metrics")
    ref_row = next(
        line for line in table.splitlines() if "`model_time_split_refinement_minutes`" in line
    )
    cells = [c.strip() for c in ref_row.split("|") if c.strip()]
    assert cells[1] == "`model_time_split_refinement_minutes`"
    assert "model time" in ref_row.lower()
    assert "refinement" in ref_row.lower()
    assert "whole minutes" in ref_row
    assert "None" in ref_row or "null" in ref_row.lower()
    del_row = next(
        line for line in table.splitlines() if "`model_time_split_delivery_minutes`" in line
    )
    assert "delivery" in del_row.lower()
    assert "whole minutes" in del_row
    # A reader of docs/metrics.md learns what the split measures, its unit,
    # and its null behaviour from the section outside the table.
    section = text.split("### Model time split (refinement against delivery)")[1]
    section = section.split("\n###")[0]
    assert "whole minutes" in section
    assert "null" in section.lower()


def test_metrics_md_metrics_table_has_self_filed_share_row():
    """AC3: docs/metrics.md's metrics table carries a row for
    self_filed_share_percent naming its unit (whole percent), its
    sprint-attribution rule (a card counts in the sprint it was filed in,
    not the sprint it merged), and its null rule (None where the sprint
    carries no filing facts) — the way every other measure's row does."""
    text = (DOCS_DIR / "metrics.md").read_text()
    table = _extract_marked_section(text, "metrics")
    row = next(line for line in table.splitlines() if "`self_filed_share_percent`" in line)
    cells = [c.strip() for c in row.split("|") if c.strip()]
    assert cells[1] == "`self_filed_share_percent`"
    assert "whole percent" in row, "row does not name the unit (whole percent)"
    assert "filed in" in row and "merged" in row, (
        "row does not name the sprint-attribution rule (filed in, not merged)"
    )
    assert "no filing facts" in row, "row does not name the null rule (None where no filing facts)"


def test_service_md_cost_example_is_complete():
    """AC7: the event-intake section has a complete cost-payload example with all
    five fields and non-negative integer values, in a copy-ready JSON block."""
    import json as json_mod

    text = (DOCS_DIR / "service.md").read_text()
    before = text.split("BEGIN:service")[0]
    # Find the JSON block after the cost payload documentation
    cost_doc_idx = before.index("A `finished` event may carry a cost payload")
    after_cost_doc = before[cost_doc_idx:]
    # Find the ```json block
    json_start = after_cost_doc.index("```json")
    json_end = after_cost_doc.index("```", json_start + 7)
    json_block = after_cost_doc[json_start + 7 : json_end]
    example = json_mod.loads(json_block)
    # All five fields are present with non-negative integer values
    for field in (
        "model_seconds",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    ):
        assert field in example, f"cost example missing field {field!r}"
        assert isinstance(example[field], int)
        assert example[field] >= 0, f"cost example field {field!r} is negative"


def test_no_documentation_shows_a_cli_flag():
    """AC6: no surviving doc page carries a sprint-metrics command line taking a
    file argument, a cards-file input (cards.json or a cards-file mount), or a
    table/markdown/Prometheus report flag."""
    pages = [(README, "README.md")] + [(DOCS_DIR / doc, doc) for doc in ALL_DOCS]
    for path, name in pages:
        text = path.read_text()
        assert "cards.json" not in text, f"{name}: references cards.json"
        for flag in ("--markdown", "--json", "--scrape"):
            assert flag not in text, f"{name}: contains report flag {flag!r}"
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"^sprint-metrics\s+\S+", stripped):
                pytest.fail(f"{name}: {line!r} looks like a sprint-metrics command with a file argument")


def test_service_md_range_row_describes_roster_answer():
    """AC5: the GET /range row in docs/service.md's generated section describes
    the roster: per-sprint completed stories, released epics and achieved Goals
    by identifier; sprints whose stories carry no links read null (no backfill).
    The /range rows are laid out per measure, so the roster content lives in its
    own row."""
    section = _extract_marked_section((DOCS_DIR / "service.md").read_text(), "service")
    range_rows = [line for line in section.splitlines() if line.startswith("| GET | /range")]
    row = next(line for line in range_rows if "roster" in line)
    for phrase in (
        "roster",
        "completed",
        "released",
        "achieved",
        "identifier",
        "null",
        "no backfill",
    ):
        assert phrase in row, f"GET /range roster row missing {phrase!r}: {row}"


def test_service_md_api_version_paragraph_describes_version_10():
    """AC: docs/service.md's api_version paragraph states the response
    api_version is '10', version '9' is retired, and intake keeps '1'."""
    text = (DOCS_DIR / "service.md").read_text()
    # The /range and /trend api_version paragraph is outside the generated section
    paragraph = text.split("The /range and /trend responses carry their own")[1]
    # Find the end of the paragraph (next blank line or next heading)
    end = paragraph.find("\n\n")
    if end == -1:
        end = len(paragraph)
    paragraph = paragraph[:end]
    assert '"10"' in paragraph
    assert '"9"' in paragraph
    assert "retired" in paragraph
    assert "10.0.0" in paragraph
    assert "Event intake" in paragraph
    assert '"1"' in paragraph


def test_metrics_md_names_dora_measures():
    """AC3: docs/metrics.md's generated table names the DORA measures with
    their plain-English display names, metric keys, units, and precision."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    # All DORA display names are present
    assert "DORA release frequency" in section
    assert "DORA lead time for changes" in section
    assert "DORA change failure rate" in section
    assert "DORA mean time to recovery" in section
    # All metric keys are present
    assert "`release_frequency`" in section
    assert "`dora_lead_time_days`" in section
    assert "`change_failure_rate_percent`" in section
    assert "`mean_time_to_recovery_minutes`" in section
    # Release frequency states its unit (whole count) and what it measures
    release_row = next(
        line for line in section.splitlines() if "`release_frequency`" in line
    )
    assert "whole count" in release_row
    assert "how often epics ship" in release_row
    # Lead time states its unit (days) and precision (mean in whole days)
    lead_row = next(
        line for line in section.splitlines() if "`dora_lead_time_days`" in line
    )
    assert "whole days" in lead_row
    assert "epic's release moment" in lead_row
    # Change-failure rate states it is a rate (share of releases that came back)
    cf_row = next(
        line for line in section.splitlines() if "`change_failure_rate_percent`" in line
    )
    assert "whole percent" in cf_row
    assert "came back with rework" in cf_row
    # MTTR states its unit (whole minutes)
    mttr_row = next(
        line for line in section.splitlines() if "`mean_time_to_recovery_minutes`" in line
    )
    assert "whole minutes" in mttr_row


def test_metrics_md_idle_time_section_states_span_minus_session_time():
    """AC: docs/metrics.md's idle-time section states the idle time is the registered
    sprint span minus the in-span session time, in whole minutes; the span is taken in
    the sprint's registered timezone; a session window is clamped to the span; a rework
    session never re-sent as 'started' reads as idle (the working-time fidelity bound);
    and a sprint with no events or no registered definition reads null (the whole span
    is not reported as idle when no session ran)."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = re.sub(
        r"\s+",
        " ",
        text.split("### Idle time against the sprint's duration", 1)[1].split("\n### ", 1)[0],
    )
    # The idle time is the registered span minus the in-span session time, in whole minutes.
    assert "registered span minus the in-span session time" in section
    assert "whole minutes" in section
    # The span is taken in the sprint's registered timezone.
    assert "registered timezone" in section
    # A session window is clamped to the span.
    assert "clamped to the span" in section
    # The working-time fidelity bound: a rework session never re-sent as 'started'
    # reads as idle.
    assert "never re-sent as" in section and "reads as idle" in section
    assert "fidelity bound" in section
    # The whole span is not reported as idle when no session ran.
    assert "whole span is not reported as idle" in section
    # The idle_minutes table row names the unit (whole minutes).
    row = next(line for line in text.splitlines() if "`idle_minutes`" in line)
    assert "whole minutes" in row
