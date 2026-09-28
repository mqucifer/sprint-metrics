"""Tests for the docs/ files structure and content."""

import re
from pathlib import Path

import pytest

from sprint_metrics._docs_gen import _generate_section_content
from sprint_metrics.thresholds import DEFAULT_THRESHOLDS

DOCS_DIR = Path(__file__).parent.parent / "docs"

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
