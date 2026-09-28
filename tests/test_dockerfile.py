"""Tests for the Dockerfile at the repository root."""

from pathlib import Path

DOCKERFILE = Path(__file__).parent.parent / "Dockerfile"


def test_dockerfile_is_not_pinned_to_an_architecture():
    """AC3: the Dockerfile contains none of the architecture-specific substrings
    amd64, arm64, x86_64, or aarch64."""
    content = DOCKERFILE.read_text()
    for arch in ("amd64", "arm64", "x86_64", "aarch64"):
        assert arch not in content, f"Dockerfile references architecture {arch!r}"
