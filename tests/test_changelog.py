"""Tests for the CHANGELOG.md file at the repository root."""

import re
import tomllib
from datetime import date
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"
PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

_HEADING_RE = re.compile(r"^## \[([^\]]+)\](.*)$", re.MULTILINE)
_DATE_RE = re.compile(r" - (\d{4}-\d{2}-\d{2})$")
_SUBHEADINGS = ["### Added", "### Changed", "### Fixed", "### Removed"]


def _parse_released_sections(content: str) -> list[dict]:
    """Return released (non-Unreleased) sections in file order.

    Each dict has keys: heading, version, date_str, date.
    """
    sections = []
    for m in _HEADING_RE.finditer(content):
        version = m.group(1)
        if version == "Unreleased":
            continue
        rest = m.group(2)
        dm = _DATE_RE.search(rest)
        date_str = dm.group(1) if dm else None
        d = None
        if date_str:
            try:
                d = date.fromisoformat(date_str)
            except ValueError:
                d = None
        sections.append(
            {"heading": m.group(0), "version": version, "date_str": date_str, "date": d}
        )
    return sections


def _version_key(v: str) -> tuple:
    return tuple(int(p) for p in v.split("."))


def check_pyproject_version(changelog_text: str, pyproject_version: str) -> list[str]:
    """Rule 1: the version in pyproject.toml equals the newest released section's version."""
    violations = []
    sections = _parse_released_sections(changelog_text)
    if not sections:
        violations.append(
            "No released sections found in CHANGELOG.md; "
            "pyproject.toml version must equal the newest released section's version"
        )
        return violations
    newest = sections[0]
    if newest["version"] != pyproject_version:
        violations.append(
            f"pyproject.toml version {pyproject_version!r} must equal the newest released "
            f"section's version, but the newest released section is "
            f"{newest['heading']!r} with version {newest['version']!r}"
        )
    return violations


def check_released_order_and_dates(changelog_text: str, check_day: date | None = None) -> list[str]:
    """Rule 2: released sections run newest-first by version; no section's date is
    later than the section above it or later than the check day."""
    violations = []
    sections = _parse_released_sections(changelog_text)
    if check_day is None:
        check_day = date.today()

    for i, sec in enumerate(sections):
        # Version ordering: each section's version must be >= the one below it
        if i + 1 < len(sections) and _version_key(sec["version"]) < _version_key(
            sections[i + 1]["version"]
        ):
            below = sections[i + 1]
            violations.append(
                f"Sections must run newest-first by version: "
                f"{sec['heading']!r} (version {sec['version']!r}) "
                f"is above {below['heading']!r} (version {below['version']!r})"
            )
        # Date ordering: this section's date must not be later than the one above
        if (
            i > 0
            and sec["date"] is not None
            and sections[i - 1]["date"] is not None
            and sec["date"] > sections[i - 1]["date"]
        ):
            above = sections[i - 1]
            violations.append(
                f"Section {sec['heading']!r} (date {sec['date_str']!r}) "
                f"is dated later than the section above it, "
                f"{above['heading']!r} (date {above['date_str']!r}); "
                f"no section's date may be later than the section above it"
            )
        # Future date check
        if sec["date"] is not None and sec["date"] > check_day:
            violations.append(
                f"Section {sec['heading']!r} is dated {sec['date_str']!r}, "
                f"which is later than the check day {check_day.isoformat()!r}; "
                f"no released section may be dated later than the check day"
            )

    return violations


def check_unreleased_first_and_subheadings(changelog_text: str) -> list[str]:
    """Rule 3: '## [Unreleased]' is the first section, with Added, Changed, Fixed,
    Removed subheadings in that order."""
    violations = []
    headings = list(_HEADING_RE.finditer(changelog_text))
    if not headings:
        violations.append("No '## [...]' headings found in CHANGELOG.md")
        return violations

    first = headings[0]
    if first.group(1) != "Unreleased":
        violations.append(
            f"First section is {first.group(0)!r}, but '## [Unreleased]' must be the first section"
        )
        return violations

    end = headings[1].start() if len(headings) > 1 else len(changelog_text)
    body = changelog_text[first.end() : end]

    positions = []
    for heading in _SUBHEADINGS:
        pos = body.find(heading)
        if pos == -1:
            violations.append(f"[Unreleased] section is missing {heading!r}")
        else:
            positions.append(pos)

    if len(positions) == len(_SUBHEADINGS) and positions != sorted(positions):
        for i in range(len(positions) - 1):
            if positions[i] > positions[i + 1]:
                violations.append(
                    f"[Unreleased] subheadings are not in order: "
                    f"{_SUBHEADINGS[i + 1]!r} appears before "
                    f"{_SUBHEADINGS[i]!r}"
                )
                break

    return violations


def check_released_headings_dated(changelog_text: str) -> list[str]:
    """Rule 4: every released section's heading is dated YYYY-MM-DD."""
    violations = []
    for sec in _parse_released_sections(changelog_text):
        if sec["date_str"] is None or sec["date"] is None:
            violations.append(f"Section heading {sec['heading']!r} is not dated with YYYY-MM-DD")
    return violations


def test_rule_pyproject_version_matches_newest_released():
    """AC1: pyproject.toml version equals the newest released section's version."""
    content = CHANGELOG.read_text()
    with open(PYPROJECT, "rb") as f:
        pyver = tomllib.load(f)["project"]["version"]

    # The real changelog passes
    assert check_pyproject_version(content, pyver) == []

    # Mutation: change the newest released section's version to a different one
    newest = _parse_released_sections(content)[0]
    parts = newest["version"].split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    bumped_version = ".".join(parts)
    mutated = content.replace(
        newest["heading"],
        newest["heading"].replace(newest["version"], bumped_version, 1),
        1,
    )
    violations = check_pyproject_version(mutated, pyver)
    assert len(violations) == 1
    assert pyver in violations[0], f"message must name pyproject version {pyver!r}: {violations[0]}"
    assert bumped_version in violations[0], (
        f"message must name the section version: {violations[0]}"
    )


def test_rule_released_sections_newest_first_and_dates_ordered():
    """AC2/AC3: released sections run newest-first by version; no date is later
    than the section above it or later than the check day."""
    content = CHANGELOG.read_text()
    check_day = date(2026, 10, 20)

    # The real changelog passes (using today's date so a future release doesn't trigger a spurious violation)
    assert check_released_order_and_dates(content) == []

    # Mutation: a higher version below a lower one (version order violation)
    mutated = content.replace("## [1.3.1]", "## [1.3.4]", 1)
    violations = check_released_order_and_dates(mutated, check_day)
    version_violations = [v for v in violations if "newest-first" in v]
    assert version_violations, f"expected a version-order violation: {violations}"
    msg = version_violations[0]
    assert "1.3.2" in msg, f"message must name the upper section's version: {msg}"
    assert "1.3.4" in msg, f"message must name the lower section's version: {msg}"

    # Mutation: a section's date later than the section above it (date order violation)
    mutated = content.replace("## [1.3.2] - 2026-10-19", "## [1.3.2] - 2026-10-20", 1)
    violations = check_released_order_and_dates(mutated, check_day)
    date_violations = [v for v in violations if "later than the section above" in v]
    assert date_violations, f"expected a date-order violation: {violations}"
    msg = date_violations[0]
    assert "1.3.2" in msg, f"message must name the offending section: {msg}"
    assert "2026-10-20" in msg, f"message must name the offending date: {msg}"

    # Mutation: a future-dated section (check-day violation)
    mutated = content.replace("## [1.3.3] - 2026-10-19", "## [1.3.3] - 2099-01-01", 1)
    violations = check_released_order_and_dates(mutated, check_day)
    future_violations = [v for v in violations if "check day" in v]
    assert future_violations, f"expected a future-date violation: {violations}"
    msg = future_violations[0]
    assert "1.3.3" in msg, f"message must name the offending section: {msg}"
    assert "2099-01-01" in msg, f"message must name the offending date: {msg}"


def test_rule_unreleased_first_with_subheadings_in_order():
    """AC4: [Unreleased] is the first section with Added, Changed, Fixed,
    Removed subheadings in that order."""
    content = CHANGELOG.read_text()

    # The real changelog passes
    assert check_unreleased_first_and_subheadings(content) == []

    # Mutation: a released section before [Unreleased]
    mutated = content.replace(
        "## [Unreleased]",
        "## [1.3.3] - 2026-10-19\n\n### Added\n\n### Changed\n\n### Fixed\n"
        "\n### Removed\n\n## [Unreleased]",
        1,
    )
    violations = check_unreleased_first_and_subheadings(mutated)
    assert violations, "expected a violation when [Unreleased] is not first"
    assert "Unreleased" in violations[0], (
        f"message must name the offending heading: {violations[0]}"
    )

    # Mutation: a missing subheading in [Unreleased]
    mutated = content.replace("### Removed\n\n## [1.3.3]", "## [1.3.3]", 1)
    violations = check_unreleased_first_and_subheadings(mutated)
    missing = [v for v in violations if "missing" in v]
    assert missing, f"expected a missing-subheading violation: {violations}"
    assert "### Removed" in missing[0], f"message must name the missing subheading: {missing[0]}"

    # Mutation: subheadings out of order in [Unreleased]
    mutated = content.replace(
        "### Changed\n\n### Fixed\n\n### Removed\n\n## [1.3.3]",
        "### Fixed\n\n### Changed\n\n### Removed\n\n## [1.3.3]",
        1,
    )
    violations = check_unreleased_first_and_subheadings(mutated)
    order = [v for v in violations if "not in order" in v]
    assert order, f"expected an order violation: {violations}"
    assert "### Fixed" in order[0], f"message must name the out-of-order subheading: {order[0]}"


def test_rule_released_headings_dated():
    """AC5: every released section's heading is dated YYYY-MM-DD."""
    content = CHANGELOG.read_text()

    # The real changelog passes
    assert check_released_headings_dated(content) == []

    # Mutation: remove a date from a section heading
    mutated = content.replace("## [1.3.3] - 2026-10-19", "## [1.3.3]", 1)
    violations = check_released_headings_dated(mutated)
    assert violations, "expected a violation for undated heading"
    assert "1.3.3" in violations[0], f"message must name the offending heading: {violations[0]}"

    # Mutation: wrong date format
    mutated = content.replace("## [1.3.3] - 2026-10-19", "## [1.3.3] - 10/19/2026", 1)
    violations = check_released_headings_dated(mutated)
    assert violations, "expected a violation for non-ISO date"
    assert "1.3.3" in violations[0], f"message must name the offending heading: {violations[0]}"
