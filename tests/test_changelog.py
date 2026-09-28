"""Tests for the CHANGELOG.md file at the repository root."""

import re
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"


def test_changelog_exists_with_correct_title_and_unreleased_section():
    """AC1: CHANGELOG.md exists, its first non-empty line is '# Changelog', and it
    contains the line '## [Unreleased]'."""
    assert CHANGELOG.exists(), "CHANGELOG.md does not exist at the repository root"
    lines = CHANGELOG.read_text().splitlines()
    first_non_empty = next(line for line in lines if line.strip())
    assert first_non_empty == "# Changelog", (
        f"first non-empty line is {first_non_empty!r}, expected '# Changelog'"
    )
    assert "## [Unreleased]" in lines, "CHANGELOG.md does not contain '## [Unreleased]'"


def test_unreleased_section_contains_standard_subheadings_in_order():
    """AC2: the text between '## [Unreleased]' and the next '## [' heading (or EOF)
    contains '### Added', '### Changed', '### Fixed', and '### Removed' in that order."""
    lines = CHANGELOG.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line == "## [Unreleased]")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ["):
            end = i
            break
    section = "\n".join(lines[start + 1 : end])
    headings = ["### Added", "### Changed", "### Fixed", "### Removed"]
    positions = []
    for heading in headings:
        assert heading in section, f"Unreleased section missing {heading!r}"
        positions.append(section.index(heading))
    assert positions == sorted(positions), f"Unreleased sub-headings are not in order: {headings}"


def test_unreleased_is_first_versioned_heading_and_no_version_before_it():
    """AC3: the first line matching '## [' followed by text and ']' is
    '## [Unreleased]', and no line matching '## [' followed by a version number
    (digits and dots) appears before it."""
    lines = CHANGELOG.read_text().splitlines()
    pattern = re.compile(r"^## \[.+\]$")
    version_pattern = re.compile(r"^## \[\d+(\.\d+)*\]$")
    matched_lines = [line for line in lines if pattern.match(line)]
    assert matched_lines, "no lines matching '## [...]' found in CHANGELOG.md"
    assert matched_lines[0] == "## [Unreleased]", (
        f"first versioned heading is {matched_lines[0]!r}, expected '## [Unreleased]'"
    )
    unreleased_idx = lines.index("## [Unreleased]")
    for line in lines[:unreleased_idx]:
        assert not version_pattern.match(line), (
            f"version-numbered heading {line!r} appears before '## [Unreleased]'"
        )
