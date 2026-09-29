"""Tests for the docs/ files structure and content."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from sprint_metrics._docs_gen import _generate_section_content
from sprint_metrics.cli import main
from sprint_metrics.thresholds import DEFAULT_THRESHOLDS

DOCS_DIR = Path(__file__).parent.parent / "docs"
README = Path(__file__).parent.parent / "README.md"

ALL_DOCS = [
    "usage.md",
    "cards.md",
    "metrics.md",
    "formats.md",
    "thresholds.md",
    "scrape.md",
]

MARKER_IDS = {
    "usage.md": "cli-args",
    "cards.md": "input-format",
    "metrics.md": "metrics",
    "formats.md": "formats",
    "thresholds.md": "thresholds",
    "scrape.md": "scrape",
}

DRIFT_FILES = [(f, MARKER_IDS[f]) for f in ALL_DOCS]


def _extract_marked_section(text: str, marker_id: str) -> str:
    """Extract the text between BEGIN:marker_id and END:marker_id."""
    pattern = rf"^BEGIN:{re.escape(marker_id)}\n(.*?)^END:{re.escape(marker_id)}\n"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"no BEGIN:{marker_id}/END:{marker_id} pair found"
    return match.group(1)


def test_all_docs_files_exist_with_markers():
    """AC1: each of the six docs/ files is non-empty, contains a BEGIN/END marker
    pair with a matching identifier, and the content between the markers is non-empty."""
    for filename in ALL_DOCS:
        path = DOCS_DIR / filename
        assert path.exists(), f"docs/{filename} does not exist"
        text = path.read_text()
        assert text.strip(), f"docs/{filename} is empty"
        marker_id = MARKER_IDS[filename]
        begin = f"BEGIN:{marker_id}"
        end = f"END:{marker_id}"
        assert begin in text, f"docs/{filename} missing {begin}"
        assert end in text, f"docs/{filename} missing {end}"
        section = _extract_marked_section(text, marker_id)
        assert section.strip(), f"docs/{filename} marked section is empty"


def test_usage_md_lists_all_arguments():
    """AC2: docs/usage.md marked section lists every positional and optional argument
    from the cli argparse parser with its help text, and outside the markers there is
    a paragraph explaining how to invoke the command."""
    path = DOCS_DIR / "usage.md"
    text = path.read_text()
    section = _extract_marked_section(text, "cli-args")

    expected_args = [
        "cards",
        "--wip-limits",
        "--escalations",
        "--sprint-date",
        "--sprint-range",
        "--prior-sprint",
        "--prior",
        "--markdown",
        "--prometheus",
        "--json",
        "--schema",
        "--scrape",
        "--port",
        "--thresholds",
        "--metrics",
    ]
    for arg in expected_args:
        assert arg in section, f"docs/usage.md marked section missing argument {arg!r}"

    before = text.split("BEGIN:cli-args")[0]
    assert before.strip(), "docs/usage.md has no hand-written content before BEGIN marker"
    assert "sprint-metrics" in before, (
        "hand-written content does not explain how to invoke the command"
    )


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


def _extract_json_block(text: str) -> list[dict]:
    """Extract the first ```json code block from markdown text."""
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert match is not None, "no ```json code block found"
    return json.loads(match.group(1))


def test_worked_example_output_matches_doc(tmp_path, capsys):
    """AC1: the worked-example JSON in docs/cards.md, run through cli.main(),
    produces a Current row byte-identical to the expected table output."""
    cards_text = (DOCS_DIR / "cards.md").read_text()
    cards = _extract_json_block(cards_text)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    current_row = [line for line in captured.out.splitlines() if line.startswith("| Current |")][0]
    assert current_row == "| Current | 5 days | 7 days | 1 | 0 | 4 days | 0% | 100% | \u2014 |"


def test_input_format_example_produces_valid_table(tmp_path, capsys):
    """AC2: the input-format example in docs/cards.md, run through cli.main() with
    default output, exits 0 and stdout contains a table header with 'Sprint' and
    a data row with 'Current'."""
    cards_text = (DOCS_DIR / "cards.md").read_text()
    cards = _extract_json_block(cards_text)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    header_rows = [line for line in captured.out.splitlines() if line.startswith("| Sprint")]
    assert header_rows, "no header row starting with '| Sprint' found"
    assert "Sprint" in header_rows[0]
    data_rows = [line for line in captured.out.splitlines() if "Current" in line]
    assert data_rows, "no data row containing 'Current' found"


def test_completed_card_excluded_from_throughput_and_cycle_time(tmp_path, capsys):
    """AC3: the worked-example input has one completed card and one in-flight card.
    The throughput cell reads '1' (not 2) and the cycle time cell reads '5 days',
    confirming the in-flight card is excluded."""
    cards_text = (DOCS_DIR / "cards.md").read_text()
    cards = _extract_json_block(cards_text)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    current_row = [line for line in captured.out.splitlines() if line.startswith("| Current |")][0]
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[3] == "1", (
        f"throughput cell is {cells[3]!r}, expected '1' (in-flight card excluded)"
    )
    assert cells[1] == "5 days", f"cycle time cell is {cells[1]!r}, expected '5 days'"


def _readme_section(text: str, heading: str) -> str:
    """Return the body of a level-2 section in README.md, up to the next level-2 heading or EOF."""
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"README.md has no section '## {heading}'"
    return match.group(1)


def test_installation_states_python_312_and_no_third_party_packages():
    """AC1 (migrated): the README's installation section states Python 3.12 is required
    and that no third-party runtime packages are needed."""
    text = README.read_text()
    section = _readme_section(text, "Installation")
    assert "3.12" in section
    assert "no third-party" in section.lower()


def test_input_format_shows_json_array_with_complete_and_partial_cards():
    """AC3 (migrated): docs/cards.md's marked section shows a JSON array of card objects
    with at least one complete example card and at least one card showing an omitted key."""
    text = (DOCS_DIR / "cards.md").read_text()
    section = _extract_marked_section(text, "input-format")
    assert '"created"' in section
    assert '"started"' in section
    assert '"completed"' in section
    assert '"blocked_since"' in section
    assert section.count('"created"') >= 2


def test_input_format_states_empty_array_is_valid():
    """AC3 (migrated): docs/cards.md states that an empty JSON array ([]) is valid input
    and produces a report in which every metric is zero."""
    text = (DOCS_DIR / "cards.md").read_text()
    before = text.split("BEGIN:input-format")[0]
    assert "[]" in before
    assert "zero" in before


def test_worked_example_incomplete_card_excluded_from_metrics(tmp_path, capsys):
    """AC (migrated): the docs/cards.md example has an incomplete card that does not
    appear in the throughput count."""
    cards_text = (DOCS_DIR / "cards.md").read_text()
    cards = _extract_json_block(cards_text)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    incomplete = [c for c in cards if not c.get("completed")]
    assert incomplete, "no card without completed field in docs/cards.md example"
    completed_count = sum(1 for c in cards if c.get("completed"))
    total_count = len(cards)
    assert completed_count < total_count
    current_row = [line for line in captured.out.splitlines() if line.startswith("| Current |")][0]
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[3] == str(completed_count)


def test_worked_example_shows_input_json_and_produces_table(tmp_path, capsys):
    """AC (migrated): the docs/cards.md worked-example JSON, run through cli.main(),
    produces a table with a header row and a Current data row."""
    cards_text = (DOCS_DIR / "cards.md").read_text()
    cards = _extract_json_block(cards_text)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "| Sprint |" in captured.out
    assert "| Current |" in captured.out


def test_worked_example_throughput_and_cycle_time_are_correct(tmp_path, capsys):
    """AC (migrated): the throughput value equals the count of completed cards in the
    docs/cards.md example, and cycle time equals the average over completed cards."""
    cards_text = (DOCS_DIR / "cards.md").read_text()
    cards = _extract_json_block(cards_text)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(cards))
    exit_code = main([str(path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    completed_cards = [c for c in cards if c.get("completed") and c.get("started")]
    expected_throughput = len([c for c in cards if c.get("completed")])
    current_row = [line for line in captured.out.splitlines() if line.startswith("| Current |")][0]
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[3] == str(expected_throughput)
    cycle_times = [
        (date.fromisoformat(c["completed"]) - date.fromisoformat(c["started"])).days
        for c in completed_cards
    ]
    if cycle_times:
        expected_cycle = round(sum(cycle_times) / len(cycle_times))
        assert cells[1] == f"{expected_cycle} days"


def test_metrics_contains_all_six_display_names():
    """AC (migrated): docs/metrics.md contains all six original metric display names."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    section_lower = section.lower()
    for name in (
        "cycle time",
        "lead time",
        "throughput",
        "wip violations",
        "blocked aging",
        "escalation rate",
    ):
        assert name in section_lower, f"missing metric name {name!r} in docs/metrics.md"


def test_metrics_reference_completed_cards_for_exclusion():
    """AC (migrated): docs/metrics.md's metric descriptions reference completed cards,
    conveying that in-flight cards are excluded from the metrics."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    assert "completed" in section.lower()


def test_cycle_time_entry_has_display_name_key_and_prometheus():
    """AC (migrated): docs/metrics.md's cycle time entry lists the display name,
    metric key, and Prometheus name, and mentions whole days."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    assert "Cycle time" in section
    assert "cycle_time_days" in section
    assert "sprint_cycle_time_days" in section
    assert "whole days" in section.lower()


def test_metrics_list_throughput_lead_time_blocked_aging_escalation():
    """AC (migrated): docs/metrics.md lists throughput, lead time, blocked aging, and
    escalation rate each with their display name, metric key, and Prometheus name."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")

    assert "Throughput" in section
    assert "throughput" in section
    assert "sprint_throughput" in section

    assert "Lead time" in section
    assert "lead_time_days" in section
    assert "sprint_lead_time_days" in section

    assert "Blocked aging" in section
    assert "blocked_aging_days" in section
    assert "sprint_blocked_aging_days" in section

    assert "Escalation rate" in section
    assert "escalation_rate_percent" in section
    assert "sprint_escalation_rate_percent" in section


def test_wip_violations_entry_has_display_name_key_and_prometheus():
    """AC (migrated): docs/metrics.md's WIP violations entry lists the display name,
    metric key, and Prometheus name."""
    text = (DOCS_DIR / "metrics.md").read_text()
    section = _extract_marked_section(text, "metrics")
    assert "WIP violations" in section
    assert "wip_violations" in section
    assert "sprint_wip_violations" in section


def test_installation_shows_uv_pip_install_with_version_tag():
    """AC1 (migrated): the README's installation section contains a uv pip install command
    with the git URL followed by a version tag."""
    text = README.read_text()
    section = _readme_section(text, "Installation")
    assert "uv pip install" in section
    assert "git+https://github.com/mqucifer/sprint-metrics.git@" in section
    match = re.search(r"sprint-metrics\.git@v\d+\.\d+\.\d+", section)
    assert match is not None, "expected a version tag like v0.1.0 after the git URL"
    assert "PATH" in section


def test_basic_usage_shows_minimal_invocation_and_stdin():
    """AC1 (migrated): the README's basic-usage section shows sprint-metrics cards.json
    and states that omitting the file argument makes the tool read JSON from standard input."""
    text = README.read_text()
    section = _readme_section(text, "Basic usage")
    assert "sprint-metrics cards.json" in section
    assert "standard input" in section.lower()


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


def test_readme_trimmed_has_no_removed_sections():
    """AC1 (migrated): README.md does not contain the removed sections or definitions."""
    text = README.read_text()
    assert "the mean (average) of the difference" not in text
    assert "## Input format" not in text
    assert "## Worked example" not in text


def test_input_format_states_created_only_required_and_top_level_array():
    """AC3 (migrated): docs/cards.md states that created is the only required field per card
    and that the top-level JSON value must be an array."""
    text = (DOCS_DIR / "cards.md").read_text()
    before = text.split("BEGIN:input-format")[0]
    assert "only" in before.lower()
    assert "created" in before
    assert "required" in before
    assert "array" in before.lower()


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


def test_formats_worked_example_empty_sprint_json(tmp_path):
    """AC4: the worked example in docs/formats.md, when run, produces the documented output."""
    import json
    import re
    import subprocess
    import sys
    from pathlib import Path

    doc = Path("docs/formats.md").read_text()

    # Extract the input JSON from the worked example section
    match = re.search(
        r"## Worked example: empty sprint\n.*?```json\n(.*?)```",
        doc,
        re.DOTALL,
    )
    assert match, "Worked example input not found in docs/formats.md"
    cards_input = match.group(1).strip()

    # Write the cards input to a temp file
    cards_file = tmp_path / "cards.json"
    cards_file.write_text(cards_input)

    # Run the command
    result = subprocess.run(
        [sys.executable, "-m", "sprint_metrics", str(cards_file), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Command failed: {result.stderr}"

    # Parse and verify the output
    output = json.loads(result.stdout)
    assert output["api_version"] == "1"
    assert output["cycle_time_days"] == 0
    assert output["lead_time_days"] == 0
    assert output["throughput"] == 0
    assert output["wip_violations"] == 0
    assert output["blocked_aging_days"] == 0
    assert output["escalation_rate_percent"] == 0
    assert output["first_attempt_rate_percent"] == 0
    assert output["failure_breakdown"] == []
    assert output["top_failure_causes"] == {}
    assert output["flags"]["cycle_time_days"] is False
    assert output["flags"]["lead_time_days"] is False
    assert output["flags"]["throughput"] is True
    assert output["flags"]["wip_violations"] is False
    assert output["flags"]["blocked_aging_days"] is False
    assert output["flags"]["escalation_rate_percent"] is False
    assert output["flags"]["first_attempt_rate_percent"] is True
