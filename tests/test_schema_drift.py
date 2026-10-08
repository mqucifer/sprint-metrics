"""Drift check: committed schema files must match the Python dicts in schema.py."""

import json
from pathlib import Path

from sprint_metrics.schema import (
    EVENT_INTAKE_SCHEMA,
    SINGLE_SPRINT_SCHEMA,
    SPRINT_RANGE_SCHEMA,
    TREND_SCHEMA,
)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

SCHEMA_FILES = [
    (SINGLE_SPRINT_SCHEMA, "single-sprint.json"),
    (SPRINT_RANGE_SCHEMA, "sprint-range.json"),
    (EVENT_INTAKE_SCHEMA, "event-intake.json"),
    (TREND_SCHEMA, "trend.json"),
]


def test_committed_schema_files_match_python_dicts():
    """Each committed schema file is byte-for-byte identical to the JSON
    serialization (indent=2) of the corresponding Python dict in schema.py."""
    drift: list[str] = []
    for schema, filename in SCHEMA_FILES:
        path = SCHEMAS_DIR / filename
        if not path.exists():
            drift.append(f"schemas/{filename}: file not found")
            continue
        expected = json.dumps(schema, indent=2)
        actual = path.read_text().rstrip("\n")
        if actual != expected:
            drift.append(f"schemas/{filename}: content does not match")
    assert not drift, "\n".join(drift)
