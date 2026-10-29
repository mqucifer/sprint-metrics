"""Temporary helper: regenerate docs/service.md from the composed fragments."""

from pathlib import Path

from sprint_metrics._docs_gen import generate_file


def test_regen_service_md():
    generate_file(Path(__file__).resolve().parent.parent / "docs" / "service.md")
