"""Scratch: regenerate the committed schemas/ and docs/ marked sections."""

from sprint_metrics._docs_gen import generate_all


def test_regenerate():
    generate_all()
