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
    """AC1: docker build exits 0 and docker run --rm sprint-metrics-test --help
    exits 0 with stdout containing 'usage: sprint-metrics'."""
    repo_root = Path(__file__).parent.parent
    build = subprocess.run(
        ["docker", "build", "-t", "sprint-metrics-test", "."],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, f"docker build failed: {build.stderr}"

    run = subprocess.run(
        ["docker", "run", "--rm", "sprint-metrics-test", "--help"],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run --help failed: {run.stderr}"
    assert "usage: sprint-metrics" in run.stdout


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_docker_run_with_cards(tmp_path):
    """AC2: docker run with a volume-mounted cards.json exits 0 and stdout
    contains a table row with the label 'Current' and a cycle-time cell ending in 'days'."""
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


def test_dockerfile_from_line_pinned_by_digest():
    dockerfile = Path("Dockerfile").read_text()
    first_line = dockerfile.splitlines()[0]
    prefix = "FROM python:3.12-slim@sha256:"
    assert first_line.startswith(prefix)
    digest = first_line[len(prefix) :]
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not available")
def test_docker_run_rejects_repeated_program_name():
    """AC3: docker run --rm sprint-metrics-test sprint-metrics --help exits non-zero,
    because 'sprint-metrics' is interpreted as the filename for the positional cards
    argument and no such file exists in the container."""
    if not _image_available():
        pytest.skip("sprint-metrics-test image not built")
    run = subprocess.run(
        ["docker", "run", "--rm", "sprint-metrics-test", "sprint-metrics", "--help"],
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
