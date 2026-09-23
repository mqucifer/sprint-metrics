"""Tests for the crew performance command."""

import json
from datetime import date

import pytest

from sprint_metrics import (
    Card,
    calculate_cycle_time_and_lead_time,
    calculate_throughput,
    calculate_wip_violations,
    format_performance_table,
    main,
)

HEADER = "| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate |"
SEPARATOR = "|--------|------------|-----------|------------|----------------|---------------|"
SEPARATOR = "|--------|------------|-----------|------------|----------------|---------------|-----------------|"

# A card completed on the 7th, started 4 days earlier and created 6 days earlier.
COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
IN_FLIGHT_CARD = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}


@pytest.fixture
def run_command(tmp_path, capsys):
    """Run the command over a sprint's cards, returning its exit code and output."""

    def run(
        cards, wip_limits=None, escalations=0, markdown=False, prometheus=False, json_output=False
    ):
        path = tmp_path / "cards.json"
        path.write_text(json.dumps(cards))
        argv = [str(path)]
        if wip_limits is not None:
            limits_path = tmp_path / "wip-limits.json"
            limits_path.write_text(json.dumps(wip_limits))
            argv += ["--wip-limits", str(limits_path)]
        if escalations:
            argv += ["--escalations", str(escalations)]
        if markdown:
            argv += ["--markdown"]
        if prometheus:
            argv += ["--prometheus"]
        if json_output:
            argv += ["--json"]
        exit_code = main(argv)
        captured = capsys.readouterr()
        return exit_code, captured.out, captured.err

    return run


def test_command_reports_cycle_and_lead_time_for_a_completed_card(run_command):
    """AC1: one card started 4 days and created 6 days before it completed shows
    a current sprint row with Cycle time 4 days and Lead time 6 days."""
    exit_code, output, _ = run_command([COMPLETED_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in output


def test_command_reports_zero_when_nothing_is_completed(run_command):
    """AC2: with no completed cards the current sprint row shows 0 days for both
    metrics, and the command exits successfully."""
    exit_code, output, _ = run_command([IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_command_reports_zero_for_an_empty_sprint(run_command):
    """A sprint with no cards at all is still a successful, well-formed report."""
    exit_code, output, _ = run_command([])

    assert exit_code == 0
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_command_reports_throughput_for_five_completed_cards(run_command):
    """AC1: when the current sprint has 5 completed cards, the table shows
    Throughput 5."""
    cards = [COMPLETED_CARD] * 5
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 5 | 0 | 0 days | 0% |" in output


def test_command_reports_throughput_zero_when_no_cards_completed(run_command):
    """AC2: when the current sprint has no completed cards, the table shows
    Throughput 0 and the command exits successfully."""
    cards = [IN_FLIGHT_CARD] * 3
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_malformed_dates_are_reported_without_a_traceback(run_command):
    exit_code, _, errors = run_command([{"created": "not-a-date"}])

    assert exit_code == 2
    assert "not-a-date" in errors


def test_cycle_and_lead_time_of_a_completed_card():
    assert calculate_cycle_time_and_lead_time([COMPLETED_CARD]) == (4, 6)


def test_in_flight_cards_do_not_count_towards_the_metrics():
    assert calculate_cycle_time_and_lead_time([IN_FLIGHT_CARD]) == (0, 0)


def test_metrics_average_across_completed_cards():
    """Two completed cards report the mean, not the total."""
    slower_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-09"}

    assert calculate_cycle_time_and_lead_time([COMPLETED_CARD, slower_card]) == (5, 7)


def test_completed_card_that_was_never_started_has_no_cycle_time():
    """Lead time is still measurable without a start date; cycle time is not."""
    card = Card(created=date(2024, 1, 1), completed=date(2024, 1, 7))

    assert calculate_cycle_time_and_lead_time([card]) == (0, 6)


def test_cards_may_be_passed_as_dataclasses():
    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3), completed=date(2024, 1, 7))

    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in format_performance_table([card])


def test_throughput_counts_completed_cards():
    """Throughput is the count of completed cards."""
    cards = [COMPLETED_CARD, IN_FLIGHT_CARD, COMPLETED_CARD]
    assert calculate_throughput(cards) == 2


def test_throughput_is_zero_when_nothing_is_completed():
    """A sprint with only in-flight cards has zero throughput."""
    cards = [IN_FLIGHT_CARD, IN_FLIGHT_CARD]
    assert calculate_throughput(cards) == 0


def test_throughput_is_zero_for_an_empty_sprint():
    """An empty sprint has zero throughput."""
    assert calculate_throughput([]) == 0


def test_command_reports_a_wip_violation_when_the_limit_is_exceeded(run_command):
    """AC1: with a WIP limit of 3 for In Progress and 4 cards in In Progress at the
    same time, the current sprint row shows WIP violations 1."""
    cards = [IN_FLIGHT_CARD] * 4
    exit_code, output, _ = run_command(cards, wip_limits={"In Progress": 3})

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 1 | 0 days | 0% |" in output


def test_command_reports_no_wip_violations_when_no_limits_are_configured(run_command):
    """AC2: with no WIP limits configured the current sprint row shows WIP
    violations 0, and the command exits successfully."""
    cards = [IN_FLIGHT_CARD] * 4
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_malformed_wip_limits_are_reported_without_a_traceback(run_command):
    exit_code, _, errors = run_command([], wip_limits=["In Progress", 3])

    assert exit_code == 2
    assert "WIP limits" in errors


def test_a_limit_met_exactly_is_not_a_violation():
    """The limit is the most cards allowed, not the first count that breaches it."""
    cards = [IN_FLIGHT_CARD] * 3

    assert calculate_wip_violations(cards, {"In Progress": 3}) == 0


def test_cards_that_overlapped_earlier_in_the_sprint_still_violate():
    """The breach counts even once the crowd has cleared: all four cards were in
    progress together on the 4th, so the report cannot show a clean board."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}] * 4

    assert calculate_wip_violations(cards, {"In Progress": 3}) == 1


def test_cards_worked_one_at_a_time_never_violate():
    """Each card leaves In Progress as the next one enters, so nothing overlaps."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-03"},
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-04"},
        {"created": "2024-01-01", "started": "2024-01-04", "completed": "2024-01-05"},
        {"created": "2024-01-01", "started": "2024-01-05", "completed": "2024-01-06"},
    ]

    assert calculate_wip_violations(cards, {"In Progress": 1}) == 0


def test_each_breached_state_counts_as_one_violation():
    """Two states over their limits are two violations; an unlimited state is none."""
    cards = [IN_FLIGHT_CARD] * 4 + [{"created": "2024-01-01"}] * 2

    limits = {"In Progress": 3, "To Do": 1, "Completed": 0}
    assert calculate_wip_violations(cards, limits) == 2
    assert calculate_wip_violations(cards, {"Completed": 0}) == 0


def test_wip_violations_are_zero_without_limits():
    """No limits configured — and an empty set of limits — cannot be violated."""
    cards = [IN_FLIGHT_CARD] * 4

    assert calculate_wip_violations(cards) == 0
    assert calculate_wip_violations(cards, {}) == 0


def test_command_reports_blocked_aging_for_a_blocked_card(run_command):
    """AC1: one card blocked for 2 days shows a current sprint row with Blocked
    aging 2 days."""
    from datetime import date, timedelta

    today = date.today()
    blocked_card = {
        "created": "2024-01-01",
        "started": "2024-01-02",
        "completed": "",
        "blocked_since": (today - timedelta(days=2)).isoformat(),
    }
    exit_code, output, _ = run_command([blocked_card])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 2 days | 0% |" in output


def test_command_reports_zero_blocked_aging_when_no_cards_blocked(run_command):
    """AC2: no cards are blocked in the current sprint, so the table shows
    Blocked aging 0 days and the command exits successfully."""
    exit_code, output, _ = run_command([COMPLETED_CARD, IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in output


def test_command_reports_escalation_rate_with_escalations(run_command):
    """AC1: with 2 escalations and 10 completed cards, the table shows
    Escalation rate 20%."""
    cards = [COMPLETED_CARD] * 10
    exit_code, output, _ = run_command(cards, escalations=2)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 10 | 0 | 0 days | 20% |" in output


def test_command_reports_zero_escalation_rate_when_no_completed_cards(run_command):
    """AC2: with no completed cards and no escalations, the table shows
    Escalation rate 0% and the command exits successfully."""
    exit_code, output, _ = run_command([IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_escalation_rate_is_zero_when_no_cards_completed():
    """With no completed cards the escalation rate is 0 regardless of escalations."""
    from sprint_metrics import calculate_escalation_rate

    assert calculate_escalation_rate([IN_FLIGHT_CARD], escalations=5) == 0


def test_escalation_rate_rounds_to_nearest_percent():
    """1 escalation out of 3 completed cards is 33.33%, which rounds to 33%."""
    from sprint_metrics import calculate_escalation_rate

    cards = [COMPLETED_CARD] * 3
    assert calculate_escalation_rate(cards, escalations=1) == 33


def test_command_reports_markdown_when_markdown_option_is_used(run_command):
    """AC1: when the markdown output option is used, the command writes a markdown
    report to standard output and does not write the table or JSON output."""
    exit_code, output, _ = run_command([COMPLETED_CARD], markdown=True)

    assert exit_code == 0
    assert "# Crew Performance Report" in output
    assert "## Current Sprint" in output
    assert "- **Cycle time**: 4 days" in output
    assert "- **Lead time**: 6 days" in output
    assert "- **Throughput**: 1 cards" in output
    assert "- **WIP violations**: 0" in output
    assert "- **Blocked aging**: 0 days" in output
    assert "- **Escalation rate**: 0%" in output
    assert HEADER not in output
    assert SEPARATOR not in output


def test_command_does_not_produce_markdown_output_by_default(run_command):
    """AC2: when the command is run without the markdown output option, it does not
    produce markdown output."""
    exit_code, output, _ = run_command([COMPLETED_CARD])

    assert exit_code == 0
    assert "# Crew Performance Report" not in output
    assert "## Current Sprint" not in output
    assert "- **Cycle time**" not in output
    assert HEADER in output
    assert SEPARATOR in output


def test_command_reports_no_performance_data_in_markdown_when_no_cards(run_command):
    """AC1 of #13: when no crew performance data is available, the markdown report
    includes 'No performance data available' and does not include the sprint's
    delivery metrics, which would all read zero for want of data.

    The heading this once asserted was absent is required by AC3 of #12, which
    has the report open the same way whether or not there is data to report.
    """
    exit_code, output, _ = run_command([], markdown=True)

    assert exit_code == 0
    assert "No performance data available" in output
    assert "## Current Sprint" not in output
    assert "- **Cycle time**" not in output
    assert "- **Lead time**" not in output
    assert "- **Throughput**" not in output
    assert "- **WIP violations**" not in output
    assert "- **Blocked aging**" not in output
    assert "- **Escalation rate**" not in output


def test_command_exits_nonzero_and_no_partial_markdown_when_data_unavailable(tmp_path, capsys):
    """AC2: when the performance command cannot access crew performance data,
    it exits with a non-zero status, writes an error to stderr, and does not
    output a partial markdown report."""
    path = tmp_path / "cards.json"
    path.write_text("not valid json")
    exit_code = main([str(path), "--markdown"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.err
    assert "No performance data available" not in captured.out
    assert "# Crew Performance Report" not in captured.out


def test_command_reports_prometheus_metrics_for_a_completed_card(run_command):
    """AC1: one card started 4 days and created 6 days before it completed shows
    Prometheus metrics with cycle time 4, lead time 6, throughput 1, and all
    other metrics at 0."""
    exit_code, output, _ = run_command([COMPLETED_CARD], prometheus=True)

    assert exit_code == 0
    assert "sprint_cycle_time_days 4" in output
    assert "sprint_lead_time_days 6" in output
    assert "sprint_throughput_cards 1" in output
    assert "sprint_wip_violations 0" in output
    assert "sprint_blocked_aging_days 0" in output
    assert "sprint_escalation_rate_percent 0" in output


def test_command_reports_prometheus_wip_violations(run_command):
    """AC2: with a WIP limit of 3 for In Progress and 4 cards in In Progress at the
    same time, the Prometheus output shows sprint_wip_violations 1."""
    cards = [IN_FLIGHT_CARD] * 4
    exit_code, output, _ = run_command(cards, wip_limits={"In Progress": 3}, prometheus=True)

    assert exit_code == 0
    assert "sprint_wip_violations 1" in output


def test_command_reports_prometheus_blocked_aging(run_command):
    """AC3: one card blocked for 2 days shows sprint_blocked_aging_days 2 in the
    Prometheus output."""
    from datetime import date, timedelta

    today = date.today()
    blocked_card = {
        "created": "2024-01-01",
        "started": "2024-01-02",
        "completed": "",
        "blocked_since": (today - timedelta(days=2)).isoformat(),
    }
    exit_code, output, _ = run_command([blocked_card], prometheus=True)

    assert exit_code == 0
    assert "sprint_blocked_aging_days 2" in output


def test_command_reports_prometheus_escalation_rate(run_command):
    """AC4: with 2 escalations and 10 completed cards, the Prometheus output shows
    sprint_escalation_rate_percent 20."""
    cards = [COMPLETED_CARD] * 10
    exit_code, output, _ = run_command(cards, escalations=2, prometheus=True)

    assert exit_code == 0
    assert "sprint_escalation_rate_percent 20" in output


def test_command_reports_prometheus_zero_for_an_empty_sprint(run_command):
    """AC5: a sprint with no cards, no WIP limits, and no escalations shows all
    Prometheus metrics at 0."""
    exit_code, output, _ = run_command([], prometheus=True)

    assert exit_code == 0
    assert "sprint_cycle_time_days 0" in output
    assert "sprint_lead_time_days 0" in output
    assert "sprint_throughput_cards 0" in output
    assert "sprint_wip_violations 0" in output
    assert "sprint_blocked_aging_days 0" in output
    assert "sprint_escalation_rate_percent 0" in output


def test_command_reports_prometheus_error_for_invalid_json(tmp_path, capsys):
    """AC6: when the cards file is not valid JSON, the command exits with code 2,
    writes an error to stderr, and does not output any Prometheus metrics."""
    path = tmp_path / "cards.json"
    path.write_text("not valid json")
    exit_code = main([str(path), "--prometheus"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "sprint-metrics:" in captured.err
    assert "sprint_cycle_time_days" not in captured.out
    assert "sprint_lead_time_days" not in captured.out
    assert "sprint_throughput_cards" not in captured.out
    assert "sprint_wip_violations" not in captured.out
    assert "sprint_blocked_aging_days" not in captured.out
    assert "sprint_escalation_rate_percent" not in captured.out


def test_command_reports_json_for_a_completed_card(run_command):
    """AC1: one completed card with cycle time 4, lead time 6, throughput 1, and
    all other metrics at 0 produces a JSON object with those values."""
    exit_code, output, _ = run_command([COMPLETED_CARD], json_output=True)

    assert exit_code == 0
    data = json.loads(output)
    assert data["cycle_time_days"] == 4
    assert data["lead_time_days"] == 6
    assert data["throughput"] == 1
    assert data["wip_violations"] == 0
    assert data["blocked_aging_days"] == 0
    assert data["escalation_rate_percent"] == 0
    assert HEADER not in output
    assert "# Crew Performance Report" not in output


def test_command_reports_json_wip_violations(run_command):
    """AC2: four cards in progress with a WIP limit of 3 produces wip_violations 1
    in the JSON output."""
    cards = [IN_FLIGHT_CARD] * 4
    exit_code, output, _ = run_command(cards, wip_limits={"In Progress": 3}, json_output=True)

    assert exit_code == 0
    data = json.loads(output)
    assert data["wip_violations"] == 1


def test_command_reports_json_escalation_rate(run_command):
    """AC3: ten completed cards with two escalations produces
    escalation_rate_percent 20 in the JSON output."""
    cards = [COMPLETED_CARD] * 10
    exit_code, output, _ = run_command(cards, escalations=2, json_output=True)

    assert exit_code == 0
    data = json.loads(output)
    assert data["escalation_rate_percent"] == 20


def test_command_reports_json_blocked_aging(run_command):
    """AC4: one card blocked for 2 days produces blocked_aging_days 2 in the
    JSON output."""
    blocked_card = {
        "created": "2024-01-01",
        "started": "2024-01-02",
        "blocked_since": "2024-01-03",
        "completed": "2024-01-05",
    }
    exit_code, output, _ = run_command([blocked_card], json_output=True)

    assert exit_code == 0
    data = json.loads(output)
    assert data["blocked_aging_days"] == 2


def test_command_reports_json_for_an_empty_sprint(run_command):
    """AC5: an empty cards list produces a JSON object with all metrics at 0."""
    exit_code, output, _ = run_command([], json_output=True)

    assert exit_code == 0
    data = json.loads(output)
    assert data["cycle_time_days"] == 0
    assert data["lead_time_days"] == 0
    assert data["throughput"] == 0
    assert data["wip_violations"] == 0
    assert data["blocked_aging_days"] == 0
    assert data["escalation_rate_percent"] == 0


def test_command_reports_json_error_for_invalid_cards_json(tmp_path, capsys):
    """AC1: when the cards input contains invalid JSON and --json is used, the
    command exits with a non-zero status, stderr is non-empty, and stdout is
    empty."""
    path = tmp_path / "cards.json"
    path.write_text("not valid json")
    exit_code = main([str(path), "--json"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.err
    assert captured.out == ""


def test_command_reports_json_error_for_wip_limits_as_array(tmp_path, capsys):
    """AC2: when the WIP limits input is a JSON array instead of an object and
    --json is used, the command exits with a non-zero status, stderr is
    non-empty, and stdout is empty."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text("[]")
    limits_path = tmp_path / "wip-limits.json"
    limits_path.write_text('["In Progress", 3]')
    exit_code = main([str(cards_path), "--wip-limits", str(limits_path), "--json"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.err
    assert captured.out == ""


def test_command_reports_json_error_for_invalid_card_date(tmp_path, capsys):
    """AC3: when a card's created value is not an ISO-8601 date and --json is
    used, the command exits with a non-zero status, stderr is non-empty, and
    stdout is empty."""
    path = tmp_path / "cards.json"
    path.write_text('[{"created": "not-a-date"}]')
    exit_code = main([str(path), "--json"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.err
    assert captured.out == ""


def test_markdown_report_includes_crew_performance_summary(run_command):
    """AC1: the markdown report starts with a heading, includes the report date,
    and shows a summary line for each of completed, in-progress, and blocked
    work with the count of cards in each state."""
    cards = [
        COMPLETED_CARD,
        IN_FLIGHT_CARD,
        {"created": "2024-01-01", "blocked_since": "2024-01-02"},
    ]
    exit_code, output, _ = run_command(cards, markdown=True)

    assert exit_code == 0
    assert output.startswith("# Crew Performance Report")
    assert "Report date:" in output
    assert "- **Completed**: 1" in output
    assert "- **In progress**: 1" in output
    assert "- **Blocked**: 1" in output


def test_markdown_report_shows_zero_for_in_progress_and_blocked_when_none(run_command):
    """AC2: when no card is in progress and none is blocked, the markdown report
    still includes all three summary lines, showing zero for in-progress and
    for blocked."""
    cards = [COMPLETED_CARD]
    exit_code, output, _ = run_command(cards, markdown=True)

    assert exit_code == 0
    assert "- **Completed**: 1" in output
    assert "- **In progress**: 0" in output
    assert "- **Blocked**: 0" in output


def test_markdown_report_for_empty_sprint(run_command):
    """AC3: an empty set of crew performance data still produces a markdown report
    that starts with a heading, includes the report date, and shows zero for all
    three summary lines."""
    exit_code, output, _ = run_command([], markdown=True)

    assert exit_code == 0
    assert output.startswith("# Crew Performance Report")
    assert "Report date:" in output
    assert "- **Completed**: 0" in output
    assert "- **In progress**: 0" in output
    assert "- **Blocked**: 0" in output


def test_markdown_summary_counts_each_card_in_one_state_only(run_command):
    """AC1: the summary lines show the count of cards in each state, so a card
    stands in exactly one of them — work held up is blocked rather than still in
    progress, and work that finished after being held up is simply completed."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "blocked_since": "2024-01-04"},
        {
            "created": "2024-01-01",
            "started": "2024-01-03",
            "completed": "2024-01-07",
            "blocked_since": "2024-01-04",
        },
    ]
    exit_code, output, _ = run_command(cards, markdown=True)

    assert exit_code == 0
    assert "- **Completed**: 1" in output
    assert "- **In progress**: 0" in output
    assert "- **Blocked**: 1" in output
