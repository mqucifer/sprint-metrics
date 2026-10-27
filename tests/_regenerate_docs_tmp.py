"""Temporary: regenerate the docs sections from the current source."""

from pathlib import Path

from sprint_metrics._docs_gen import generate_file


def test_regenerate_docs_sections():
    root = Path(__file__).resolve().parent.parent
    for relative in ("docs/metrics.md", "docs/thresholds.md", "docs/service.md"):
        path = root / relative
        if path.exists():
            generate_file(path)
