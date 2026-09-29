from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
DEPENDBOT_PATH = REPO_ROOT / ".github" / "dependabot.yml"


def _load_dependabot():
    with DEPENDBOT_PATH.open() as f:
        return yaml.safe_load(f)


def test_dependabot_version_and_updates_structure():
    """AC1: version is 2, updates has a docker entry at / with weekly schedule."""
    config = _load_dependabot()
    assert config["version"] == 2
    updates = config["updates"]
    assert isinstance(updates, list)
    docker_entries = [u for u in updates if u["package-ecosystem"] == "docker"]
    assert len(docker_entries) >= 1
    entry = docker_entries[0]
    assert entry["directory"] == "/"
    assert entry["schedule"]["interval"] == "weekly"


def test_dependabot_only_docker_and_root_directory():
    """AC2: no entry has a package-ecosystem other than docker, no entry has a directory other than /."""
    config = _load_dependabot()
    updates = config["updates"]
    for entry in updates:
        assert entry["package-ecosystem"] == "docker"
        assert entry["directory"] == "/"
