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


def test_changelog_1_0_0_section_has_date_entry_and_unreleased_above():
    """AC2: [1.0.0] has a date suffix, the release entry under Added, and [Unreleased] above it."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    content = changelog.read_text()

    # [1.0.0] heading with date suffix in the form '## [1.0.0] - YYYY-MM-DD'
    match = re.search(r"^## \[1\.0\.0\] - \d{4}-\d{2}-\d{2}$", content, re.MULTILINE)
    assert match, "Missing '## [1.0.0] - YYYY-MM-DD' heading"

    # [Unreleased] section appears above [1.0.0]
    unreleased_match = re.search(r"^## \[Unreleased\]$", content, re.MULTILINE)
    assert unreleased_match, "Missing '## [Unreleased]'"
    assert unreleased_match.start() < match.start()

    # The release entry appears under ### Added in the [1.0.0] section
    after_100 = content[match.end() :]
    next_heading = re.search(r"^## ", after_100, re.MULTILINE)
    section = after_100[: next_heading.start()] if next_heading else after_100

    added_section = re.search(
        r"^### Added\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL
    )
    assert added_section, "No ### Added subsection in [1.0.0]"
    entry = added_section.group(1)
    assert "Sprint-metrics CLI: cycle time, lead time, throughput" in entry
    assert "WIP-limit violations" in entry
    assert "blocked-card aging" in entry
    assert "first-attempt rate" in entry
    assert "failure breakdown" in entry


def test_changelog_1_0_1_section_dated_with_entry_and_unreleased_above():
    """AC2: [1.0.1] has a date suffix, [Unreleased] above it contains only standard
    subheadings with no entries, and [1.0.0] below remains with its date and entry."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    content = changelog.read_text()

    # [1.0.1] heading with date suffix in the form '## [1.0.1] - YYYY-MM-DD'
    match = re.search(r"^## \[1\.0\.1\] - \d{4}-\d{2}-\d{2}$", content, re.MULTILINE)
    assert match, "Missing '## [1.0.1] - YYYY-MM-DD' heading"

    # [Unreleased] section appears above [1.0.1]
    unreleased_match = re.search(r"^## \[Unreleased\]$", content, re.MULTILINE)
    assert unreleased_match, "Missing '## [Unreleased]'"
    assert unreleased_match.start() < match.start()

    # [Unreleased] section contains only the four standard subheadings with no entries
    after_unreleased = content[unreleased_match.end() :]
    next_heading = re.search(r"^## \[", after_unreleased, re.MULTILINE)
    unreleased_section = (
        after_unreleased[: next_heading.start()] if next_heading else after_unreleased
    )
    assert not re.search(r"^\s*-\s", unreleased_section, re.MULTILINE), (
        "[Unreleased] section contains entries; it should only have subheadings"
    )

    # [1.0.0] section below [1.0.1] remains with its date
    match_100 = re.search(r"^## \[1\.0\.0\] - 2025-07-13$", content, re.MULTILINE)
    assert match_100, "Missing '## [1.0.0] - 2025-07-13' heading"
    assert match_100.start() > match.start(), "[1.0.0] should appear below [1.0.1]"


def test_pyproject_version_is_1_0_2():
    """AC1: pyproject.toml version field reads 1.0.2 with other fields unchanged."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    project = data["project"]
    assert project["version"] == "1.0.2"
    assert project["name"] == "sprint-metrics"
    assert project["description"] == "Delivery metrics for the crew's own board."
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == []


def test_changelog_heading_order_unreleased_1_0_2_1_0_1_1_0_0():
    """AC2: versioned headings in order are [Unreleased], [1.0.2] - date,
    [1.0.1] - 2025-07-14, [1.0.0] - 2025-07-13; no other versioned heading
    between Unreleased and 1.0.0."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    lines = changelog.read_text().splitlines()
    pattern = re.compile(r"^## \[.+\]")
    matched_lines = [line for line in lines if pattern.match(line)]
    assert len(matched_lines) >= 4, (
        f"Expected at least 4 versioned headings, got {len(matched_lines)}"
    )
    assert matched_lines[0] == "## [Unreleased]", (
        f"First heading is {matched_lines[0]!r}, expected '## [Unreleased]'"
    )
    second = matched_lines[1]
    assert re.match(r"^## \[1\.0\.2\] - \d{4}-\d{2}-\d{2}$", second), (
        f"Second heading is {second!r}, expected '## [1.0.2] - YYYY-MM-DD'"
    )
    assert matched_lines[2] == "## [1.0.1] - 2025-07-14", (
        f"Third heading is {matched_lines[2]!r}, expected '## [1.0.1] - 2025-07-14'"
    )
    assert matched_lines[3] == "## [1.0.0] - 2025-07-13", (
        f"Fourth heading is {matched_lines[3]!r}, expected '## [1.0.0] - 2025-07-13'"
    )
    # No version-numbered heading before [Unreleased]
    unreleased_idx = lines.index("## [Unreleased]")
    version_pattern = re.compile(r"^## \[\d+(\.\d+)*\]")
    for line in lines[:unreleased_idx]:
        assert not version_pattern.match(line), (
            f"Version-numbered heading {line!r} appears before '## [Unreleased]'"
        )
