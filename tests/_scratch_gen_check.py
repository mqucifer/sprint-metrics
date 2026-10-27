import re
from pathlib import Path

from sprint_metrics._docs_gen import _generate_metrics_content

DOCS = Path(__file__).resolve().parent.parent / "docs"


def _extract(text: str, marker_id: str) -> str:
    pattern = rf"^BEGIN:{re.escape(marker_id)}\n(.*?)^END:{re.escape(marker_id)}\n"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match is not None
    return match.group(1)


def test_metrics_section_matches_generated():
    committed = (DOCS / "metrics.md").read_text()
    committed_section = _extract(committed, "metrics")
    generated = _generate_metrics_content()
    assert committed_section == generated, "committed metrics section drifted from generated content"
