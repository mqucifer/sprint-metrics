"""Tests that both entry points start the service and refuse report arguments."""

import os
import subprocess
import sys

import pytest

from sprint_metrics.service import RETIRED_MESSAGE

RETIRED_ARGUMENTS = [
    ["cards.json"],
    ["--scrape"],
    ["--service"],
    ["--json"],
    ["--sprint-range", "2024-01..2024-02"],
]


def _run(argv, env=None):
    return subprocess.run(
        [sys.executable, "-m", "sprint_metrics", *argv],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _env_without_db():
    env = dict(os.environ)
    env.pop("SPRINT_METRICS_DB", None)
    return env


@pytest.mark.parametrize("argv", RETIRED_ARGUMENTS)
def test_python_minus_m_refuses_report_arguments(argv):
    """AC5: python -m sprint_metrics given a report argument exits non-zero and
    says the command-line report tool has been retired."""
    result = _run(argv)

    assert result.returncode != 0
    assert RETIRED_MESSAGE in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("argv", RETIRED_ARGUMENTS)
def test_console_script_refuses_report_arguments_like_python_minus_m(argv, capsys):
    """AC5: the console script's target rejects each argument exactly as
    python -m sprint_metrics does: the same exit code and message."""
    from sprint_metrics.service import main

    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == _run(argv).returncode
    assert captured.err.strip() == RETIRED_MESSAGE


def test_python_minus_m_without_arguments_or_database_names_the_database():
    """AC5: with no arguments and SPRINT_METRICS_DB unset, python -m sprint_metrics
    exits non-zero naming the missing database."""
    result = _run([], env=_env_without_db())

    assert result.returncode != 0
    assert "SPRINT_METRICS_DB" in result.stderr


def test_python_minus_m_help_describes_the_service_only():
    """AC3: --help exits 0 with a usage line naming sprint-metrics, describing the
    service and carrying no report flag."""
    result = _run(["--help"])

    assert result.returncode == 0
    assert result.stdout.startswith("usage: sprint-metrics")
    assert "SPRINT_METRICS_DB" in result.stdout
    for flag in (
        "--json",
        "--markdown",
        "--prometheus",
        "--scrape",
        "--service",
        "--sprint-range",
        "--prior",
        "--thresholds",
        "--metrics",
        "--wip-limits",
        "--escalations",
        "--sprint-date",
        "--port",
        "--schema",
        "cards",
    ):
        assert flag not in result.stdout


def test_console_script_targets_the_service_entry():
    """AC1: pyproject.toml's console script points at the service's entry."""
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())

    assert pyproject["project"]["scripts"] == {"sprint-metrics": "sprint_metrics.service:main"}
