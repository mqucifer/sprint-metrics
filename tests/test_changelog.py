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


def test_pyproject_version_is_1_3_0():
    """AC1: pyproject.toml version field reads 1.3.0 with other fields unchanged."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    project = data["project"]
    assert project["version"] == "1.3.0"
    assert project["name"] == "sprint-metrics"
    assert project["description"] == "Delivery metrics for the crew's own board."
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == [
        "psycopg>=3.1",
        "opentelemetry-sdk>=1.24",
        "opentelemetry-exporter-otlp>=1.24",
    ]


def test_changelog_1_3_0_section_content():
    """AC2: the [1.3.0] - 2026-10-13 section sits directly below [Unreleased], with
    six Added bullets, one Changed bullet, and three Fixed bullets."""
    import re
    from pathlib import Path

    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    content = changelog.read_text()

    match = re.search(r"^## \[1\.3\.0\] - 2026-10-13$", content, re.MULTILINE)
    assert match, "Missing '## [1.3.0] - 2026-10-13' heading"

    # Positioned directly between [Unreleased] and [1.2.0]
    unreleased = re.search(r"^## \[Unreleased\]$", content, re.MULTILINE)
    assert unreleased and unreleased.start() < match.start()
    v120 = re.search(r"^## \[1\.2\.0\] - 2026-10-10$", content, re.MULTILINE)
    assert v120 and match.start() < v120.start()

    after = content[match.end() :]
    next_version = re.search(r"^## \[", after, re.MULTILINE)
    section = after[: next_version.start()] if next_version else after

    added_match = re.search(r"^### Added\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL)
    assert added_match, "No ### Added subsection in [1.3.0]"
    added = added_match.group(1)
    added_bullets = [line for line in added.splitlines() if line.startswith("- ")]
    assert len(added_bullets) == 6, f"Expected 6 Added entries in [1.3.0], got {len(added_bullets)}"
    for phrase in [
        "superseded",
        "replaced_by",
        "Superseded column",
        "Prometheus",
        "cycle_time_minutes",
        "lead_time_minutes",
        "card_created_at",
    ]:
        assert phrase in added, f"[1.3.0] Added missing {phrase!r}"

    changed_match = re.search(
        r"^### Changed\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL
    )
    assert changed_match, "No ### Changed subsection in [1.3.0]"
    changed = changed_match.group(1)
    changed_bullets = [line for line in changed.splitlines() if line.startswith("- ")]
    assert len(changed_bullets) == 1, (
        f"Expected 1 Changed entry in [1.3.0], got {len(changed_bullets)}"
    )
    assert "in-progress" in changed, "[1.3.0] Changed missing 'in-progress'"
    assert "blocked" in changed, "[1.3.0] Changed missing 'blocked'"

    fixed_match = re.search(r"^### Fixed\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL)
    assert fixed_match, "No ### Fixed subsection in [1.3.0]"
    fixed = fixed_match.group(1)
    fixed_bullets = [line for line in fixed.splitlines() if line.startswith("- ")]
    assert len(fixed_bullets) == 3, f"Expected 3 Fixed entries in [1.3.0], got {len(fixed_bullets)}"
    for phrase in ["/sprint", "space", "escalation rate", "0 to 100", "/range"]:
        assert phrase in fixed, f"[1.3.0] Fixed missing {phrase!r}"


def test_changelog_unreleased_empty_after_1_3_0_release():
    """AC3: [Unreleased] retains its four standard subheadings with no entries
    beneath them; the released entries now sit in [1.3.0]."""
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

    subheadings = ["### Added", "### Changed", "### Fixed", "### Removed"]
    for heading in subheadings:
        assert heading in section_lines, f"[Unreleased] missing {heading!r}"

    for heading in subheadings:
        idx = section_lines.index(heading)
        for j in range(idx + 1, len(section_lines)):
            line = section_lines[j]
            if line.startswith("### ") or line.startswith("## "):
                break
            assert not line.startswith("- "), (
                f"Entry {line!r} found under {heading!r} in [Unreleased]"
            )

    content = "\n".join(lines)
    match = re.search(r"^## \[1\.3\.0\] - 2026-10-13$", content, re.MULTILINE)
    assert match, "Missing '## [1.3.0] - 2026-10-13'"
    after = content[match.end() :]
    next_version = re.search(r"^## \[", after, re.MULTILINE)
    section = after[: next_version.start()] if next_version else after
    added_match = re.search(r"^### Added\s*\n(.*?)(?=^### |\Z)", section, re.MULTILINE | re.DOTALL)
    assert added_match, "No ### Added in [1.3.0]"
    added = added_match.group(1)
    assert "card_created_at" in added, "card_created_at entry not in [1.3.0] Added"
