"""Tests for the CHANGELOG.md file at the repository root."""

import re
import tomllib
from datetime import date
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"
PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
CHANGES = Path(__file__).parent.parent / "changes"

_HEADING_RE = re.compile(r"^## \[([^\]]+)\](.*)$", re.MULTILINE)
_DATE_RE = re.compile(r" - (\d{4}-\d{2}-\d{2})$")
# towncrier's fragments, in Keep a Changelog's sections (mqucifer/crew#1010).
_KINDS = ["added", "changed", "deprecated", "removed", "fixed", "security"]
_FRAGMENT_RE = re.compile(rf"^(\+[^./]+|\d+)\.({'|'.join(_KINDS)})(\.\d+)?\.md$")
_NOT_FRAGMENTS = {"README.md", ".gitkeep"}
_START = "<!-- towncrier release notes start -->"


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


def _unreleased_body_span(content: str) -> tuple[int, int]:
    """Return (start, end) char positions of the [Unreleased] section body.

    start is just after the '## [Unreleased]' heading line.
    end is the start of the next '## [...]' heading (or end of content).
    """
    headings = list(_HEADING_RE.finditer(content))
    first = headings[0]
    assert first.group(1) == "Unreleased"
    end = headings[1].start() if len(headings) > 1 else len(content)
    return first.end(), end


def _subheading_bodies(content: str, subheading: str) -> list[str]:
    """Return the body text of every section that has the given subheading line."""
    bodies = []
    for m in re.finditer(rf"^{re.escape(subheading)}\s*$", content, re.MULTILINE):
        start = m.end()
        next_h = re.search(r"^### |^## \[", content[start:], re.MULTILINE)
        end = start + next_h.start() if next_h else len(content)
        bodies.append(content[start:end])
    return bodies


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


def check_fragments_and_start_line(changelog_text: str, fragment_names: list[str]) -> list[str]:
    """Rule 3: changes waiting for a release are towncrier fragments in changes/, each
    named <issue>.<kind>.md with <kind> a Keep a Changelog section, and CHANGELOG.md has
    towncrier's start line above every released section, where a release writes its own."""
    violations = []
    for name in fragment_names:
        if name in _NOT_FRAGMENTS:
            continue
        if not _FRAGMENT_RE.match(name):
            violations.append(
                f"changes/{name} is not a fragment: name it <issue>.<kind>.md, <kind> one of "
                f"{', '.join(_KINDS)}"
            )
    start = changelog_text.find(_START)
    if start == -1:
        violations.append(f"CHANGELOG.md has no towncrier start line {_START!r}")
        return violations
    released = _parse_released_sections(changelog_text)
    if released and changelog_text.index(released[0]["heading"]) < start:
        violations.append(
            f"Released section {released[0]['heading']!r} is above the towncrier start line "
            f"{_START!r}: a release writes its section below it"
        )
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
    # Judge the mutations on the day of the newest release, so each release
    # cut on a later day does not itself read as future-dated.
    check_day = max(s["date"] for s in _parse_released_sections(content))

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


def test_rule_fragments_and_start_line():
    """Rule 3: what waits is towncrier fragments in changes/, and CHANGELOG.md has
    towncrier's start line above every released section (mqucifer/crew#1010)."""
    content = CHANGELOG.read_text()
    names = sorted(p.name for p in CHANGES.iterdir())

    # The real changelog and fragments pass
    assert check_fragments_and_start_line(content, names) == []
    assert "README.md" in names

    # Each kind, with an issue, with none, and with a counter, is a fragment
    good = [f"944.{kind}.md" for kind in _KINDS] + ["+docs.fixed.md", "944.fixed.2.md"]
    assert check_fragments_and_start_line(content, good) == []

    # Mutation: a file in changes/ that isn't a fragment
    violations = check_fragments_and_start_line(content, ["944.improved.md"])
    assert violations, "expected a violation for a kind Keep a Changelog doesn't have"
    assert "944.improved.md" in violations[0], f"message must name the file: {violations[0]}"

    # Mutation: no start line
    violations = check_fragments_and_start_line(content.replace(_START, "", 1), names)
    assert violations and _START in violations[0], f"must name the start line: {violations}"

    # Mutation: a released section above the start line
    newest = _parse_released_sections(content)[0]["heading"]
    mutated = content.replace(_START, "", 1).replace(newest, f"{newest}\n\n{_START}", 1)
    violations = check_fragments_and_start_line(mutated, names)
    assert violations and newest in violations[0], f"must name the section: {violations}"


def test_rule_leaves_unreleased_entries_from_before_fragments_alone():
    """An entry a branch wrote under [Unreleased] before the switch is collected by the
    next release, so it breaks no rule meanwhile."""
    content = CHANGELOG.read_text().replace(
        _START, f"{_START}\n\n## [Unreleased]\n\n### Fixed\n\n- An old-way fix\n", 1
    )
    assert check_fragments_and_start_line(content, []) == []
    with open(PYPROJECT, "rb") as f:
        assert check_pyproject_version(content, tomllib.load(f)["project"]["version"]) == []


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


def test_unreleased_added_names_session_event():
    """The changelog names the intake accepting a 'session' event,
    in whichever section the entry currently sits in."""
    content = CHANGELOG.read_text()
    added = _subheading_bodies(content, "### Added")
    assert any(
        "session" in body and "intake" in body and "accepts" in body for body in added
    )


def test_unreleased_added_names_session_epics():
    """AC6: CHANGELOG.md records that /range now answers each epic's
    in-sprint session time, in whichever section the entry currently sits in."""
    content = CHANGELOG.read_text()
    added = _subheading_bodies(content, "### Added")
    added_section = "\n".join(added)
    assert "session_epics" in added_section
    assert "epic" in added_section
    assert "in-sprint session minutes" in added_section


def test_unreleased_changed_names_api_version_move():
    """The changelog names the response api_version move,
    in whichever section the entry currently sits in."""
    content = CHANGELOG.read_text()
    changed = _subheading_bodies(content, "### Changed")
    assert any('"11"' in body for body in changed)
    assert any('"12"' in body for body in changed)
    assert any("api_version" in body for body in changed)


def test_unreleased_changed_says_how_much_past_numbers_move():
    """The changelog's Changed entry says by how much past numbers move:
    working time, idle time, cost and model-time-split now read from session
    records; Sprint 38's working time moves from 72 to about 22; cost and
    model-time move from no data to real values; sprints with no session record
    read null; a story with no session record reads unknown, never zero;
    flat prior/delta names keep their shape under the new api_version."""
    content = CHANGELOG.read_text()
    changed = _subheading_bodies(content, "### Changed")
    changed_section = "\n".join(changed)
    # The answers now read from session records instead of span windows / cost payload
    assert "session records" in changed_section
    assert "span" in changed_section
    # Sprint 38's worked example: 72 to about 22
    assert "Sprint 38" in changed_section
    assert "72" in changed_section
    assert "22" in changed_section
    # Cost and model-time move from no data to real values
    assert "no data" in changed_section
    assert "real values" in changed_section
    # Sprints with no session record read null (unknown)
    assert "null" in changed_section
    assert "unknown" in changed_section
    # A story with no session record reads unknown, never zero
    assert "never zero" in changed_section
    # Flat prior/delta names keep their shape under the new api_version
    assert "prior" in changed_section
    assert "api_version" in changed_section

