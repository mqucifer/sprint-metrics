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
    """AC2: [1.0.1] has a date suffix, [Unreleased] above it contains standard
    subheadings, and [1.0.0] below remains with its date and entry."""
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

    # [Unreleased] section contains the four standard subheadings in order
    after_unreleased = content[unreleased_match.end() :]
    next_heading = re.search(r"^## \[", after_unreleased, re.MULTILINE)
    unreleased_section = (
        after_unreleased[: next_heading.start()] if next_heading else after_unreleased
    )
    headings = ["### Added", "### Changed", "### Fixed", "### Removed"]
    positions = []
    for heading in headings:
        assert heading in unreleased_section, f"[Unreleased] section missing {heading!r}"
        positions.append(unreleased_section.index(heading))
    assert positions == sorted(positions), "[Unreleased] sub-headings are not in order"

    # [1.0.0] section below [1.0.1] remains with its date
    match_100 = re.search(r"^## \[1\.0\.0\] - 2025-07-13$", content, re.MULTILINE)
    assert match_100, "Missing '## [1.0.0] - 2025-07-13' heading"
    assert match_100.start() > match.start(), "[1.0.0] should appear below [1.0.1]"


def test_changelog_1_1_0_section_has_stateful_service_entry():
    """AC5: the [1.1.0] section has exactly four subheadings in order; the first
    non-blank line after '### Added' is a bullet containing the five required
    substrings; and zero bullet lines under Changed, Fixed, and Removed."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    lines = changelog.read_text().splitlines()

    start = None
    for i, line in enumerate(lines):
        if re.match(r"^## \[1\.1\.0\] - \d{4}-\d{2}-\d{2}$", line):
            start = i
            break
    assert start is not None, "Missing '## [1.1.0] - YYYY-MM-DD' heading"

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    section_lines = lines[start + 1 : end]

    subheadings = ["### Added", "### Changed", "### Fixed", "### Removed"]
    found_headings = [line for line in section_lines if line.startswith("### ")]
    assert found_headings == subheadings, (
        f"Subheadings are {found_headings}, expected {subheadings}"
    )

    added_idx = section_lines.index("### Added")
    next_idx = added_idx + 1
    while next_idx < len(section_lines) and section_lines[next_idx].strip() == "":
        next_idx += 1
    assert next_idx < len(section_lines), "No content after ### Added"
    first_line = section_lines[next_idx]
    assert first_line.startswith("- "), (
        f"Line after ### Added is {first_line!r}, expected to start with '- '"
    )
    for substring in [
        "board events over HTTP",
        "Postgres",
        "Prometheus /metrics",
        "health-check",
        "schema",
    ]:
        assert substring in first_line, f"Line after ### Added missing {substring!r}"

    for heading in ["### Changed", "### Fixed", "### Removed"]:
        heading_idx = section_lines.index(heading)
        for j in range(heading_idx + 1, len(section_lines)):
            line = section_lines[j]
            if line.startswith("### ") or line.startswith("## "):
                break
            assert not line.startswith("- "), f"Bullet line {line!r} found under {heading!r}"


def test_changelog_1_1_0_date_is_valid_and_after_1_0_2():
    """AC6: the date in the [1.1.0] heading is a valid ISO date strictly after
    2025-07-15 (the [1.0.2] release date)."""
    import re
    from datetime import date
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    content = changelog.read_text()

    match = re.search(r"^## \[1\.1\.0\] - (\d{4}-\d{2}-\d{2})$", content, re.MULTILINE)
    assert match, "Missing '## [1.1.0] - YYYY-MM-DD' heading"

    parsed = date.fromisoformat(match.group(1))
    assert parsed > date(2025, 7, 15), (
        f"[1.1.0] date {match.group(1)} is not after [1.0.2] date 2025-07-15"
    )


def test_pyproject_version_is_1_2_0():
    """AC1: pyproject.toml version field reads 1.2.0 with other fields unchanged."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    project = data["project"]
    assert project["version"] == "1.2.0"
    assert project["name"] == "sprint-metrics"
    assert project["description"] == "Delivery metrics for the crew's own board."
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == [
        "psycopg>=3.1",
        "opentelemetry-sdk>=1.24",
        "opentelemetry-exporter-otlp>=1.24",
    ]


def test_changelog_1_2_0_section_content():
    """AC2: the [1.2.0] - 2026-10-10 section has the required entries under
    Added (ten bullets) and Changed (two bullets)."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    content = changelog.read_text()

    match = re.search(r"^## \[1\.2\.0\] - 2026-10-10$", content, re.MULTILINE)
    assert match, "Missing '## [1.2.0] - 2026-10-10' heading"

    # Positioned between [Unreleased] and [1.1.0]
    unreleased = re.search(r"^## \[Unreleased\]$", content, re.MULTILINE)
    assert unreleased and unreleased.start() < match.start()
    v110 = re.search(r"^## \[1\.1\.0\] - \d{4}-\d{2}-\d{2}$", content, re.MULTILINE)
    assert v110 and v110.start() > match.start()

    after = content[match.end() :]
    next_version = re.search(r"^## \[", after, re.MULTILINE)
    section = after[: next_version.start()] if next_version else after

    # Added subsection: ten bullets, each required topic present
    added_match = re.search(r"^### Added\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL)
    assert added_match, "No ### Added subsection in [1.2.0]"
    added = added_match.group(1)
    added_bullets = [line for line in added.splitlines() if line.startswith("- ")]
    assert len(added_bullets) == 10, (
        f"Expected 10 Added entries in [1.2.0], got {len(added_bullets)}"
    )

    added_checks = [
        "/trend",
        "OpenTelemetry",
        "OTEL_",
        "trace span",
        "structured log",
        "schemas/",
        "attempt failed",
        "Free-form sprint names",
        "Points delivered",
        "first-attempt counts",
        "escalation count",
        "failure-breakdown",
        "503",
        "POST /sprints",
        "Automatic recovery",
    ]
    for phrase in added_checks:
        assert phrase in added, f"[1.2.0] Added missing {phrase!r}"

    # Changed subsection: two bullets, each required topic present
    changed_match = re.search(
        r"^### Changed\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL
    )
    assert changed_match, "No ### Changed subsection in [1.2.0]"
    changed = changed_match.group(1)
    changed_bullets = [line for line in changed.splitlines() if line.startswith("- ")]
    assert len(changed_bullets) == 2, (
        f"Expected 2 Changed entries in [1.2.0], got {len(changed_bullets)}"
    )

    changed_checks = [
        "start date",
        "Null metrics",
        "schemas allowing null",
    ]
    for phrase in changed_checks:
        assert phrase in changed, f"[1.2.0] Changed missing {phrase!r}"


def test_changelog_heading_order_unreleased_1_2_0_1_1_0_1_0_2_1_0_1_1_0_0():
    """AC2/AC3: versioned headings in order are [Unreleased], [1.2.0] - 2026-10-10,
    [1.1.0] - date, [1.0.2] - 2025-07-15, [1.0.1] - 2025-07-14, [1.0.0] - 2025-07-13;
    no version-numbered heading before [Unreleased]."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    lines = changelog.read_text().splitlines()
    pattern = re.compile(r"^## \[.+\]")
    matched_lines = [line for line in lines if pattern.match(line)]
    assert len(matched_lines) == 6, (
        f"Expected exactly 6 versioned headings, got {len(matched_lines)}"
    )
    assert matched_lines[0] == "## [Unreleased]", (
        f"First heading is {matched_lines[0]!r}, expected '## [Unreleased]'"
    )
    assert matched_lines[1] == "## [1.2.0] - 2026-10-10", (
        f"Second heading is {matched_lines[1]!r}, expected '## [1.2.0] - 2026-10-10'"
    )
    second = matched_lines[2]
    assert re.match(r"^## \[1\.1\.0\] - \d{4}-\d{2}-\d{2}$", second), (
        f"Third heading is {second!r}, expected '## [1.1.0] - YYYY-MM-DD'"
    )
    assert matched_lines[3] == "## [1.0.2] - 2025-07-15", (
        f"Fourth heading is {matched_lines[3]!r}, expected '## [1.0.2] - 2025-07-15'"
    )
    assert matched_lines[4] == "## [1.0.1] - 2025-07-14", (
        f"Fifth heading is {matched_lines[4]!r}, expected '## [1.0.1] - 2025-07-14'"
    )
    assert matched_lines[5] == "## [1.0.0] - 2025-07-13", (
        f"Sixth heading is {matched_lines[5]!r}, expected '## [1.0.0] - 2025-07-13'"
    )
    # No version-numbered heading before [Unreleased]
    unreleased_idx = lines.index("## [Unreleased]")
    version_pattern = re.compile(r"^## \[\d+(\.\d+)*\]")
    for line in lines[:unreleased_idx]:
        assert not version_pattern.match(line), (
            f"Version-numbered heading {line!r} appears before '## [Unreleased]'"
        )


def test_changelog_unreleased_empty_after_1_2_0_release():
    """AC3: [Unreleased] retains its four standard subheadings with no entries
    beneath them; the two former entries appear in [1.2.0] under Added."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    lines = changelog.read_text().splitlines()

    start = next(i for i, line in enumerate(lines) if line == "## [Unreleased]")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ["):
            end = i
            break
    section_lines = lines[start + 1 : end]

    # Four standard subheadings present
    subheadings = ["### Added", "### Changed", "### Fixed", "### Removed"]
    for heading in subheadings:
        assert heading in section_lines, f"[Unreleased] missing {heading!r}"

    # No bullet entries under any subheading
    for heading in subheadings:
        idx = section_lines.index(heading)
        for j in range(idx + 1, len(section_lines)):
            line = section_lines[j]
            if line.startswith("### ") or line.startswith("## "):
                break
            assert not line.startswith("- "), (
                f"Entry {line!r} found under {heading!r} in [Unreleased]"
            )

    # The two former entries are in [1.2.0] Added
    content = "\n".join(lines)
    match = re.search(r"^## \[1\.2\.0\] - 2026-10-10$", content, re.MULTILINE)
    assert match, "Missing '## [1.2.0] - 2026-10-10'"
    after = content[match.end() :]
    next_version = re.search(r"^## \[", after, re.MULTILINE)
    section = after[: next_version.start()] if next_version else after
    added_match = re.search(r"^### Added\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL)
    assert added_match, "No ### Added in [1.2.0]"
    added = added_match.group(1)
    assert "POST /sprints" in added, "POST /sprints entry not in [1.2.0] Added"
    assert "Automatic recovery" in added, "Automatic recovery entry not in [1.2.0] Added"
