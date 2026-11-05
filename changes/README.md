# Changelog fragments

Each change that ships adds one file here, and never edits `CHANGELOG.md`:
`<issue>.<kind>.md`, holding one line on what changed for someone using sprint-metrics.
`<issue>` is the issue's number, or `+<name>` for a change with none. `<kind>` is the
Keep a Changelog section it fits: `added`, `changed`, `deprecated`, `removed`, `fixed`
or `security`.

A release builds its `CHANGELOG.md` section from the fragments, as `towncrier build
--version X.Y.Z` does with the setup in `pyproject.toml`, and deletes them
(mqucifer/crew#1010).
