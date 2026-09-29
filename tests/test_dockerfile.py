"""Tests for the Dockerfile at the repository root."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DOCKERFILE = Path(__file__).parent.parent / "Dockerfile"


def test_dockerfile_is_not_pinned_to_an_architecture():
    """AC3: the Dockerfile contains none of the architecture-specific substrings
    amd64, arm64, x86_64, or aarch64."""
    content = DOCKERFILE.read_text()
    for arch in ("amd64", "arm64", "x86_64", "aarch64"):
        assert arch not in content, f"Dockerfile references architecture {arch!r}"


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_docker_build_and_help():
    """AC1: docker build exits 0 and docker run sprint-metrics-test sprint-metrics --help
    exits 0 with stdout containing 'sprint-metrics'."""
    repo_root = Path(__file__).parent.parent
    build = subprocess.run(
        ["docker", "build", "-t", "sprint-metrics-test", "."],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, f"docker build failed: {build.stderr}"

    run = subprocess.run(
        ["docker", "run", "--rm", "sprint-metrics-test", "sprint-metrics", "--help"],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run --help failed: {run.stderr}"
    assert "sprint-metrics" in run.stdout


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_docker_run_with_cards(tmp_path):
    """AC2: docker run with a volume-mounted cards.json exits 0 and stdout
    contains the expected table row for a card with cycle time 5 days and
    lead time 7 days."""
    if not _image_available():
        pytest.skip("sprint-metrics-test image not built")
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(
        json.dumps([{"created": "2024-01-03", "started": "2024-01-05", "completed": "2024-01-10"}])
    )

    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cards_path}:/input/cards.json",
            "sprint-metrics-test",
            "sprint-metrics",
            "/input/cards.json",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run failed: {run.stderr}"
    assert "| Current | 5 days | 7 days | 1 | 0 | 0 days | 0% | 100% | \u2014 |" in run.stdout


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_docker_runs_as_non_root():
    """AC1: the container's process runs as a non-root user (UID != 0)."""
    if not _image_available():
        pytest.skip("sprint-metrics-test image not built")
    run = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", "sprint-metrics-test", "-c", "id -u"],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run id -u failed: {run.stderr}"
    uid = int(run.stdout.strip())
    assert uid != 0, f"Process runs as root (UID {uid})"


def _image_available():
    """Return True if the sprint-metrics-test image exists in the local Docker daemon."""
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", "sprint-metrics-test"],
        capture_output=True,
    )
    return result.returncode == 0


def test_dockerfile_from_line_has_valid_sha256_digest():
    """AC1: The FROM line's @sha256: digest is exactly 64 hex characters,
    and the FROM line contains 'python' and '3.12' before the '@'."""
    content = DOCKERFILE.read_text()
    from_lines = [line.strip() for line in content.splitlines() if line.strip().startswith("FROM")]
    assert len(from_lines) == 1, f"Expected exactly one FROM line, found {len(from_lines)}"
    from_line = from_lines[0]
    assert "@" in from_line, f"FROM line has no digest: {from_line}"
    before_at, after_at = from_line.split("@", 1)
    assert "python" in before_at, f"FROM line before '@' missing 'python': {from_line}"
    assert "3.12" in before_at, f"FROM line before '@' missing '3.12': {from_line}"
    assert after_at.startswith("sha256:"), f"Digest prefix is not sha256: {after_at[:10]}"
    digest = after_at.removeprefix("sha256:")
    assert len(digest) == 64, f"Digest length is {len(digest)}, expected 64"
    assert all(c in "0123456789abcdef" for c in digest), f"Digest contains non-hex chars: {digest}"


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_docker_build_and_help_with_digest():
    """AC2: docker build exits 0 and docker run sprint-metrics-digest sprint-metrics --help
    exits 0 with stdout containing 'usage:'."""
    repo_root = Path(__file__).parent.parent
    build = subprocess.run(
        ["docker", "build", "-t", "sprint-metrics-digest", "."],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, f"docker build failed: {build.stderr}"

    run = subprocess.run(
        ["docker", "run", "--rm", "sprint-metrics-digest", "sprint-metrics", "--help"],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run --help failed: {run.stderr}"
    assert "usage:" in run.stdout


def test_dockerfile_from_line_no_bare_tag():
    """AC3: The FROM line's image reference ends with @sha256:<64-hex>,
    with no bare-tag reference (pattern ':<tag>' with no subsequent '@sha256:')."""
    content = DOCKERFILE.read_text()
    from_lines = [line.strip() for line in content.splitlines() if line.strip().startswith("FROM")]
    assert len(from_lines) == 1, f"Expected exactly one FROM line, found {len(from_lines)}"
    from_line = from_lines[0]
    image_ref = from_line.split(" ", 1)[1] if " " in from_line else from_line
    assert "@sha256:" in image_ref, f"FROM line has no @sha256: digest: {from_line}"
    digest_part = image_ref.split("@sha256:")[1]
    assert len(digest_part) == 64, (
        f"Digest after @sha256: has length {len(digest_part)}, expected 64"
    )
    assert all(c in "0123456789abcdef" for c in digest_part), "Digest contains non-hex characters"
