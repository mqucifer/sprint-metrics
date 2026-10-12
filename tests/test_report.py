"""Tests for the single-sprint formatters in sprint_metrics.report."""

from sprint_metrics.report import format_markdown_report, format_performance_table


def test_format_performance_table_completed_card():
    """AC1: one completed card (created 2024-01-01, started 2024-01-03, completed
    2024-01-07) with no WIP limits, no escalations, and no prior cards produces
    a table containing the Current row with 4 days cycle time and 6 days lead time."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    result = format_performance_table([card])
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 | 0 days | 0% |" in result


def test_format_markdown_report_empty_cards():
    """AC2: an empty list of cards produces a markdown report containing
    'No performance data available' and not containing '## Current Sprint'."""
    result = format_markdown_report([])
    assert "No performance data available" in result
    assert "## Current Sprint" not in result


def test_format_performance_table_thresholds_flag_cycle_time_only():
    """AC3: one completed card with cycle time 4 days and thresholds
    {"cycle_time_days": 3} produces a table where the cycle time cell has a
    warning marker but the lead time cell does not."""
    card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
    result = format_performance_table([card], thresholds={"cycle_time_days": 3})
    assert "| Current | 4 days \u26a0\ufe0f | 6 days | 1 | 0 | 0 | 0 days | 0% |" in result


def test_card_detail_shows_attempts_and_failure_class():
    """AC2: a completed card with attempts=2 and failure_class='parse' shows both values in its Card Detail row."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 2,
        "failure_class": "parse",
    }
    result = format_markdown_report([card])
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    data_lines = [
        line
        for line in lines[detail_idx + 4 :]
        if line.startswith("|") and not line.startswith("|-")
    ]
    assert len(data_lines) == 1
    assert "2" in data_lines[0]
    assert "parse" in data_lines[0]


def test_card_detail_shows_blocked_since_date():
    """AC4: a blocked card's blocked_since date appears in its Card Detail row."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-02",
        "blocked_since": "2024-01-05",
    }
    result = format_markdown_report([card])
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    section_body = "\n".join(lines[detail_idx:])
    assert "2024-01-05" in section_body


def test_card_detail_one_line_per_card_with_correct_dates():
    """AC6: exactly one data line per card, with blocked_since on the same line as its created date."""
    cards = [
        {"created": "2024-07-01", "started": "2024-07-02", "completed": "2024-07-05"},
        {"created": "2024-07-03", "started": "2024-07-05"},
        {"created": "2024-07-03", "started": "2024-07-04", "blocked_since": "2024-07-07"},
    ]
    result = format_markdown_report(cards)
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    data_lines = [
        line
        for line in lines[detail_idx + 4 :]
        if line.startswith("|") and not line.startswith("|-")
    ]
    assert len(data_lines) == 3
    for line in data_lines:
        assert "2024-07-01" in line or "2024-07-03" in line
    blocked_lines = [line for line in data_lines if "2024-07-07" in line]
    assert len(blocked_lines) == 1
    assert "2024-07-03" in blocked_lines[0]


def test_card_detail_shows_attempts_failure_class_and_role():
    """AC7: a completed card shows its attempts, failure_class, and failure_role in its Card Detail row."""
    card = {
        "created": "2024-01-01",
        "started": "2024-01-03",
        "completed": "2024-01-07",
        "attempts": 3,
        "failure_class": "timeout",
        "failure_role": "infra",
    }
    result = format_markdown_report([card])
    lines = result.splitlines()
    detail_idx = lines.index("## Card Detail")
    data_lines = [
        line
        for line in lines[detail_idx + 4 :]
        if line.startswith("|") and not line.startswith("|-")
    ]
    assert len(data_lines) == 1
    assert "3" in data_lines[0]
    assert "timeout" in data_lines[0]
    assert "infra" in data_lines[0]


def test_card_detail_section_after_definitions_shows_both_cards():
    """AC1: Card Detail appears after Definitions and lists both cards by created date."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "started": "2024-01-04"},
    ]
    result = format_markdown_report(cards)
    lines = result.splitlines()
    assert lines.index("## Card Detail") > lines.index("## Definitions")
    section_body = "\n".join(lines[lines.index("## Card Detail") :])
    assert "2024-01-01" in section_body
    assert "2024-01-02" in section_body


def test_card_detail_omitted_when_no_cards():
    """AC3: with no cards, the report has Definitions but no Card Detail section."""
    result = format_markdown_report([])
    assert "## Definitions" in result
    assert "## Card Detail" not in result


def test_table_superseded_shows_count_and_points():
    """AC1: header has Superseded after Throughput before WIP violations; cell is '2 (8 pts)'."""
    from sprint_metrics.report import format_performance_table

    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "superseded": True, "superseded_because": "sponsor", "points": 5},
        {
            "created": "2024-01-03",
            "superseded": True,
            "superseded_because": "story_problem",
            "points": 3,
        },
    ]
    result = format_performance_table(cards)
    lines = result.splitlines()
    header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
    assert header_cells.index("Superseded") == header_cells.index("Throughput") + 1
    assert header_cells.index("Superseded") == header_cells.index("WIP violations") - 1
    current_row = next(line for line in lines if line.startswith("| Current |"))
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[4] == "2 (8 pts)"


def test_table_superseded_zero_shows_bare_zero():
    """AC2: with 1 completed card and no superseded, the full row matches exactly."""
    from sprint_metrics.report import format_performance_table

    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
    ]
    result = format_performance_table(cards)
    lines = result.splitlines()
    current_row = next(line for line in lines if line.startswith("| Current |"))
    assert current_row == "| Current | 4 days | 6 days | 1 | 0 | 0 | 0 days | 0% | 100% | \u2014 |"
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[4] == "0"


def test_table_empty_sprint_superseded_zero():
    """AC3: empty sprint exits 0 and Superseded cell is '0'."""
    from sprint_metrics.report import format_performance_table

    result = format_performance_table([])
    lines = result.splitlines()
    current_row = next(line for line in lines if line.startswith("| Current |"))
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[4] == "0"


def test_table_prior_superseded_delta():
    """AC4: prior row Superseded '0', current '1 (5 pts)', delta '+1'."""
    from sprint_metrics.report import format_performance_table

    current_cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "superseded": True, "superseded_because": "sponsor", "points": 5},
    ]
    prior_cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
    ]
    result = format_performance_table(current_cards, prior_cards=prior_cards)
    lines = result.splitlines()
    prior_row = next(line for line in lines if line.startswith("| Prior |"))
    current_row = next(line for line in lines if line.startswith("| Current |"))
    delta_row = next(line for line in lines if line.startswith("| Delta |"))
    prior_cells = [c.strip() for c in prior_row.split("|") if c.strip()]
    current_cells = [c.strip() for c in current_row.split("|") if c.strip()]
    delta_cells = [c.strip() for c in delta_row.split("|") if c.strip()]
    assert prior_cells[4] == "0"
    assert current_cells[4] == "1 (5 pts)"
    assert delta_cells[4] == "+1"


def test_table_header_superseded_position_and_separator():
    """AC5: header exact string, 'Superseded' is 5th pipe-delimited cell, separator 5th cell is 12 dashes."""
    from sprint_metrics.report import format_performance_table

    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "state": "Superseded", "points": 5},
        {"created": "2024-01-03", "state": "Superseded", "points": 3},
    ]
    result = format_performance_table(cards)
    lines = result.splitlines()
    header = lines[0]
    separator = lines[1]
    assert header == (
        "| Sprint | Cycle time | Lead time | Throughput | Superseded | WIP violations |"
        " Blocked aging | Escalation rate | First attempt | Top causes |"
    )
    header_cells = [c.strip() for c in header.split("|") if c.strip()]
    assert header_cells[4] == "Superseded"
    separator_cells = [c.strip() for c in separator.split("|") if c.strip()]
    assert separator_cells[4] == "-" * 12


def test_table_superseded_no_points_shows_zero_pts():
    """AC6: superseded card with no points field shows '1 (0 pts)'."""
    from sprint_metrics.report import format_performance_table

    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "superseded": True, "superseded_because": "sponsor"},
    ]
    result = format_performance_table(cards)
    lines = result.splitlines()
    current_row = next(line for line in lines if line.startswith("| Current |"))
    cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert cells[4] == "1 (0 pts)"


def test_table_metrics_filtered_superseded_only():
    """AC7: --metrics 'throughput,superseded_count' shows exactly 3 columns."""
    from sprint_metrics.report import format_performance_table

    cards = [
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"},
        {"created": "2024-01-02", "superseded": True, "superseded_because": "sponsor", "points": 5},
        {"created": "2024-01-03", "superseded": True, "superseded_because": "sponsor", "points": 3},
        {
            "created": "2024-01-04",
            "superseded": True,
            "superseded_because": "story_problem",
            "points": 7,
        },
    ]
    result = format_performance_table(cards, metrics=frozenset({"throughput", "superseded_count"}))
    lines = result.splitlines()
    header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
    assert header_cells == ["Sprint", "Throughput", "Superseded"]
    current_row = next(line for line in lines if line.startswith("| Current |"))
    current_cells = [c.strip() for c in current_row.split("|") if c.strip()]
    assert len(current_cells) == 3
    assert current_cells[1] == "1"
    assert current_cells[2] == "3 (15 pts)"
