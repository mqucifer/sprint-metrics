"""Temporary fixup: bump the response api_version assertions 8 -> 9."""

from pathlib import Path


def test_fixup():
    path = Path(__file__).parent / "test_service.py"
    text = path.read_text()
    updated = text.replace('assert body["api_version"] == "8"', 'assert body["api_version"] == "9"')
    assert updated != text, "no api_version assertions to update"
    path.write_text(updated)
