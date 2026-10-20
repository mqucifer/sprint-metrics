# 11. CI checks the changelog by rules, not per-release pins

- **Date:** 2026-10-20
- **Status:** Accepted

## Context

Every release cut to date had to edit at least one merged test, because each release was pinned by its own test. The changelog's invariants lived only inside `tests/test_changelog.py`, and a contributor discovered them, if at all, by reading the test source.

## Decision

CI checks `CHANGELOG.md` by rules that hold for every release:

1. The version in `pyproject.toml` equals the newest released section's version in `CHANGELOG.md`.
2. Released sections run newest first by version, and no released section's date is later than the date of the section above it or later than the day the check runs.
3. `## [Unreleased]` is the first section, with the subheadings Added, Changed, Fixed, and Removed in that order.
4. Every released section's heading is dated `YYYY-MM-DD`.

A section's content — the entries under its subheadings — is not checked by tests; entries are checked by review, not by CI.

## Consequences

Cutting a release adds its own dated section, bumps `pyproject.toml`, and changes no merged test. The two documents — this ADR and README.md's Versioning section — state the same four rules in the same order.

## Source

mqucifer/sprint-metrics#692 ([issue](https://github.com/mqucifer/sprint-metrics/issues/692)); its records R1–R4 (2026-10-20); supersedes mqucifer/sprint-metrics ADR 0003.
