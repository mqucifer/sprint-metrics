"""Tests for the _docs_gen module."""

import pytest


def test_generated_metrics_section_contains_required_content():
    """AC1: the generated metrics section contains 'Cycle time', 'cycle_time_days',
    and the first non-empty line of calculate_cycle_time_and_lead_time's docstring."""
    from sprint_metrics._docs_gen import _generate_metrics_content
    from sprint_metrics.metrics import calculate_cycle_time_and_lead_time

    content = _generate_metrics_content()
    assert "Cycle time" in content
    assert "cycle_time_days" in content
    doc_lines = [
        line for line in calculate_cycle_time_and_lead_time.__doc__.splitlines() if line.strip()
    ]
    assert doc_lines[0].strip() in content


def test_generate_file_preserves_handwritten_content(tmp_path):
    """AC2: hand-written content before BEGIN and after END is preserved; the
    placeholder between the markers is replaced with generated text."""
    from sprint_metrics._docs_gen import generate_file

    doc_path = tmp_path / "metrics.md"
    intro = "Hand-written intro\n"
    begin = "BEGIN:metrics\n"
    placeholder = "placeholder text\n"
    end = "END:metrics\n"
    outro = "Hand-written outro\n"

    original = intro + begin + placeholder + end + outro
    doc_path.write_text(original)

    intro_offset = original.index("Hand-written intro")

    generate_file(doc_path)

    result = doc_path.read_text()
    assert result.index("Hand-written intro") == intro_offset
    assert "Hand-written outro" in result
    assert "placeholder text" not in result
    assert "Cycle time" in result


def test_generate_file_missing_begin_marker(tmp_path, capsys):
    """AC3: a file with no BEGIN marker causes generate_file to raise SystemExit(1),
    write an error to stderr containing the file's path, and leave the file unchanged."""
    from sprint_metrics._docs_gen import generate_file

    doc_path = tmp_path / "metrics.md"
    original_content = "Just some text without any markers.\n"
    doc_path.write_text(original_content)

    with pytest.raises(SystemExit) as exc_info:
        generate_file(doc_path)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert str(doc_path) in captured.err
    assert doc_path.read_text() == original_content
