"""Tests for pyproject.toml dependency declarations."""

from pathlib import Path


def test_pyproject_declares_three_runtime_dependencies():
    """AC1: pyproject.toml [project] dependencies contains exactly the three
    required runtime packages."""
    import tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    deps = data["project"]["dependencies"]
    assert "psycopg>=3.1" in deps
    assert "opentelemetry-sdk>=1.24" in deps
    assert "opentelemetry-exporter-otlp>=1.24" in deps
    assert len(deps) == 3
