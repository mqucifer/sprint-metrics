"""Temporary: regenerate the committed schema files from the Python dicts."""

from pathlib import Path

from sprint_metrics._docs_gen import _generate_schema_files


def test_regenerate_committed_schema_files():
    _generate_schema_files(Path(__file__).resolve().parent.parent / "schemas")
