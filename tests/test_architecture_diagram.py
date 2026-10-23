"""Tests for the repository's C4 diagram of record, docs/architecture.md."""

import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent / "docs"
ARCH = DOCS_DIR / "architecture.md"

C4_DIAGRAM_TYPES = (
    "C4Context",
    "C4Container",
    "C4Component",
    "C4Dynamic",
    "C4Deployment",
)


def _mermaid_blocks(text: str) -> list[str]:
    """Return the body of each mermaid block, without the fences."""
    return re.findall(r"^```mermaid\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


def test_architecture_md_draws_c4_diagram_blocks():
    """AC: docs/architecture.md exists and every mermaid block opens with a C4
    diagram type, so the repository's C4 diagram renders."""
    assert ARCH.exists(), "docs/architecture.md does not exist"
    text = ARCH.read_text()
    blocks = _mermaid_blocks(text)
    assert len(blocks) >= 3, "expected context, container and component diagrams"
    for block in blocks:
        first_line = block.lstrip().splitlines()[0].strip()
        assert first_line in C4_DIAGRAM_TYPES, (
            f"mermaid block opens with {first_line!r}, not a C4 diagram type"
        )


def test_architecture_diagram_draws_the_system_as_built():
    """The diagram names the three runtime modes, the Postgres schema, and the
    module that owns all SQL, as the code has them."""
    text = ARCH.read_text()
    for name in ("CLI", "Scrape server", "Stateful service", "Postgres", "store.py"):
        assert name in text, f"diagram is missing {name!r}"
