"""Scratch: bump the api_version assertions from "7" to "8" in the test files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bump_api_version_assertions():
    service_tests = ROOT / "tests" / "test_service.py"
    text = service_tests.read_text()
    old = 'assert body["api_version"] == "7"'
    new = 'assert body["api_version"] == "8"'
    count = text.count(old)
    assert count == 9, f"expected 9, found {count}"
    service_tests.write_text(text.replace(old, new))

    imports_tests = ROOT / "tests" / "test_package_imports.py"
    text = imports_tests.read_text()
    old = 'assert report.API_VERSION == "7"'
    new = 'assert report.API_VERSION == "8"'
    assert text.count(old) == 1
    imports_tests.write_text(text.replace(old, new))
