"""Tests for the health status summary in the markdown standup report."""

import json

from sprint_metrics import main


def test_markdown_health_summary_all_clear(tmp_path, capsys):
    """AC1: a completed card with cycle time 4, lead time 6, throughput 1 and no
    --thresholds flag produces 'Status: All clear' between the report date and
    the first section heading, and no 'Breached:' text."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    date_idx = next(i for i, line in enumerate(lines) if line.startswith("Report date:"))
    heading_idx = next(i for i, line in enumerate(lines) if line.startswith("## "))
    between = lines[date_idx + 1 : heading_idx]
    assert "Status: All clear" in between
    assert "Breached:" not in output


def test_markdown_health_summary_breached_metrics(tmp_path, capsys):
    """AC2: a completed card with cycle time 7, lead time 9, throughput 1 produces
    'Status: Attention needed (2 metrics breached)' with the two breached metric
    bullets between the status line and the first section heading."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-10"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    status_idx = next(i for i, line in enumerate(lines) if line.startswith("Status:"))
    heading_idx = next(
        i for i, line in enumerate(lines) if i > status_idx and line.startswith("## ")
    )
    between = lines[status_idx + 1 : heading_idx]
    assert "Status: Attention needed (2 metrics breached)" in output
    assert "- Cycle time: 7 days (threshold 5 days)" in between
    assert "- Lead time: 9 days (threshold 7 days)" in between


def test_markdown_health_summary_in_progress_card_breaches(tmp_path, capsys):
    """AC3: a card with only a created date (in progress, not completed, not
    blocked) produces 'Status: Attention needed (2 metrics breached)' with
    throughput and first-attempt rate bullets, and the ## Current Sprint heading
    still appears after the health summary."""
    card = {"created": "2024-01-01"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    status_idx = next(i for i, line in enumerate(lines) if line.startswith("Status:"))
    heading_idx = next(
        i for i, line in enumerate(lines) if i > status_idx and line.startswith("## ")
    )
    between = lines[status_idx + 1 : heading_idx]
    assert "Status: Attention needed (2 metrics breached)" in output
    assert "- Throughput: 0 cards (threshold 1 card)" in between
    assert "- First attempt rate: 0% (threshold 80%)" in between
    assert lines[heading_idx].startswith("## ")


def test_markdown_health_summary_empty_cards_no_status(tmp_path, capsys):
    """AC4: an empty cards file produces 'No performance data available' and no
    'Status:' or 'Breached:' text."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text("[]")
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "No performance data available" in output
    assert "Status:" not in output
    assert "Breached:" not in output


def test_markdown_health_summary_breached_bullets_contiguous(tmp_path, capsys):
    """AC6: when two or more metrics breach, the Status line and every bullet are
    contiguous (no blank between Status and first bullet, no blank between
    consecutive bullets), and a single blank line separates the last bullet from
    the next ## heading."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-10"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    status_idx = next(i for i, line in enumerate(lines) if line.startswith("Status:"))
    # The line immediately after Status starts with '- ' (no blank between)
    assert lines[status_idx + 1].startswith("- ")
    # Find the first ## heading after Status
    heading_idx = next(
        i for i, line in enumerate(lines) if i > status_idx and line.startswith("## ")
    )
    # The line before the heading is blank (single blank separator)
    assert lines[heading_idx - 1] == ""
    # All lines between Status and the blank-before-heading start with '- '
    between = lines[status_idx + 1 : heading_idx - 1]
    assert all(line.startswith("- ") for line in between)


def test_markdown_health_summary_breached_bullets_in_canonical_order(tmp_path, capsys):
    """AC7: when both cycle_time and first_attempt_rate breach, the cycle time
    bullet appears before the first-attempt rate bullet, matching the canonical
    metric order."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"},
        {"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"},
        {"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"},
        {
            "created": "2024-01-01",
            "started": "2024-01-01",
            "completed": "2024-01-08",
            "attempts": 2,
        },
        {
            "created": "2024-01-01",
            "started": "2024-01-01",
            "completed": "2024-01-08",
            "attempts": 2,
        },
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    cycle_idx = next(i for i, line in enumerate(lines) if line.startswith("- Cycle time:"))
    first_attempt_idx = next(
        i for i, line in enumerate(lines) if line.startswith("- First attempt rate:")
    )
    assert cycle_idx < first_attempt_idx


def test_markdown_health_summary_all_clear_no_content_between_status_and_heading(tmp_path, capsys):
    """AC8: when no metric breaches, the line after 'Status: All clear' is blank,
    followed by the next ## heading; no bullets, no 'Breached:', no other content
    appear between the Status line and the section heading."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    status_idx = next(i for i, line in enumerate(lines) if line == "Status: All clear")
    # Next line is blank
    assert lines[status_idx + 1] == ""
    # Line after that starts with ##
    assert lines[status_idx + 2].startswith("## ")


def test_markdown_health_summary_cycle_time_bullet_exact_format(tmp_path, capsys):
    """AC9: the cycle time bullet reads exactly '- Cycle time: 7 days (threshold
    5 days)' with the unit 'days' in both the value and the threshold."""
    card = {"created": "2024-01-01", "started": "2024-01-01", "completed": "2024-01-08"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "- Cycle time: 7 days (threshold 5 days)" in output


def test_attention_line_blocked_and_in_progress(tmp_path, capsys):
    """AC1: one blocked card (blocked 5 days) and one in-progress card produce
    'Attention: 1 blocked (5 days), 1 in progress' in the health summary section,
    between the Status line and the ## Current Sprint heading."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-26"},
        {"created": "2024-01-15", "started": "2024-01-20"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    attention_idx = next(i for i, line in enumerate(lines) if line.startswith("Attention:"))
    assert lines[attention_idx] == "Attention: 1 blocked (5 days), 1 in progress"
    status_idx = next(i for i, line in enumerate(lines) if line.startswith("Status:"))
    heading_idx = next(
        i for i, line in enumerate(lines) if i > status_idx and line.startswith("## ")
    )
    assert status_idx < attention_idx < heading_idx


def test_no_attention_line_when_only_completed(tmp_path, capsys):
    """AC2: a completed card with no blocked or in-progress cards produces no
    'Attention:' line in the markdown output."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([card]))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Attention:" not in output


def test_no_attention_line_empty_cards(tmp_path, capsys):
    """AC3: an empty cards file produces 'No performance data available' and does
    not include the text 'Attention:'."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text("[]")
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "No performance data available" in output
    assert "Attention:" not in output


def test_attention_line_max_block_duration(tmp_path, capsys):
    """AC4: two blocked cards (one blocked 3 days, one blocked 7 days) and no
    in-progress cards produce 'Attention: 2 blocked (7 days), 0 in progress'."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-28"},
        {"created": "2024-01-01", "blocked_since": "2024-01-24"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Attention: 2 blocked (7 days), 0 in progress" in output


def test_attention_line_shows_max_not_sum_or_min(tmp_path, capsys):
    """AC5: the line reads exactly 'Attention: 2 blocked (7 days), 1 in progress'
    and the number in parentheses is 7 (the maximum block duration), not 3 or 10."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-28"},
        {"created": "2024-01-01", "blocked_since": "2024-01-24"},
        {"created": "2024-01-15", "started": "2024-01-20"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    attention_line = next(line for line in lines if line.startswith("Attention:"))
    assert attention_line == "Attention: 2 blocked (7 days), 1 in progress"
    assert "(3 days)" not in attention_line
    assert "(10 days)" not in attention_line


def test_blocked_card_not_counted_as_in_progress(tmp_path, capsys):
    """AC6: a blocked card (blocked_since set, not completed) with a started date
    is counted only as blocked, not also as in progress."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-28", "started": "2024-01-02"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Attention: 1 blocked (3 days), 0 in progress" in output


def test_attention_line_last_in_health_summary(tmp_path, capsys):
    """AC7: the Attention line is the last line of the health summary block; the
    line immediately after it is blank, followed by the next ## heading."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-26"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    attention_idx = next(i for i, line in enumerate(lines) if line.startswith("Attention:"))
    assert lines[attention_idx + 1] == ""
    assert lines[attention_idx + 2].startswith("## ")


def test_attention_counts_match_summary(tmp_path, capsys):
    """AC8: the blocked count in the Attention line equals the 'Blocked' count in
    the Summary, and the in-progress count equals the 'In progress' count; a card
    that is both started and blocked is counted only as blocked."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-28", "started": "2024-01-02"},
        {"created": "2024-01-15", "started": "2024-01-20"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown", "--sprint-date", "2024-01-31"])
    output = capsys.readouterr().out
    assert exit_code == 0
    lines = output.splitlines()
    attention_line = next(line for line in lines if line.startswith("Attention:"))
    assert "1 blocked" in attention_line
    assert "1 in progress" in attention_line
    assert "- **Blocked**: 1" in output
    assert "- **In progress**: 1" in output


def test_attention_line_shows_duration_without_sprint_date(tmp_path, capsys):
    """When --sprint-date is not provided, the Attention line still shows a
    duration in parentheses, consistent with the Blocked aging metric which
    defaults to date.today()."""
    cards = [
        {"created": "2024-01-01", "blocked_since": "2024-01-26"},
    ]
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    exit_code = main([str(cards_path), "--markdown"])
    output = capsys.readouterr().out
    assert exit_code == 0
    attention_line = next(line for line in output.splitlines() if line.startswith("Attention:"))
    assert " days)" in attention_line
