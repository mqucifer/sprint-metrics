"""Temporary helper: regenerate the docs' marked sections and the schema files."""

from sprint_metrics._docs_gen import generate_all


def test_dump_generated():
    generate_all()
    assert True
