"""Tests for the DORA measures in sprint_metrics.dora."""

from datetime import UTC, datetime


def test_release_frequency_returns_count():
    """The release frequency is the count of distinct epics released."""
    from sprint_metrics.dora import calculate_release_frequency

    assert calculate_release_frequency(["E1", "E2"]) == 2
    assert calculate_release_frequency(["E1"]) == 1
    assert calculate_release_frequency([]) == 0


def test_release_frequency_none_when_no_epic_link():
    """None when no release can be derived (no epic link on any story)."""
    from sprint_metrics.dora import calculate_release_frequency

    assert calculate_release_frequency(None) is None


def test_dora_lead_time_returns_mean_in_whole_days():
    """The lead time is the mean of the spans, rounded to the nearest whole day."""
    from sprint_metrics.dora import calculate_dora_lead_time

    # 4 stories with spans of 3, 4, 5, 6 days → mean = 4.5 → rounds to 4
    assert calculate_dora_lead_time([3.0, 4.0, 5.0, 6.0]) == 4
    # 2 stories with spans of 3, 5 days → mean = 4.0 → rounds to 4
    assert calculate_dora_lead_time([3.0, 5.0]) == 4
    # 1 story with span of 7 days → mean = 7.0 → rounds to 7
    assert calculate_dora_lead_time([7.0]) == 7


def test_dora_lead_time_none_when_no_epic_link():
    """None when no release can be derived (no epic link on any story)."""
    from sprint_metrics.dora import calculate_dora_lead_time

    assert calculate_dora_lead_time(None) is None


def test_dora_lead_time_none_when_empty_list():
    """None when the list of spans is empty."""
    from sprint_metrics.dora import calculate_dora_lead_time

    assert calculate_dora_lead_time([]) is None


def test_calculate_dora_returns_block_with_both_values():
    """The DORA block carries release_frequency and lead_time_days."""
    from sprint_metrics.dora import calculate_dora

    result = calculate_dora(["E1", "E2"], [3.0, 4.0, 5.0, 6.0])
    assert result == {"release_frequency": 2, "lead_time_days": 4}


def test_calculate_dora_null_values_when_no_epic_link():
    """Both values are None when no release can be derived."""
    from sprint_metrics.dora import calculate_dora

    result = calculate_dora(None, None)
    assert result == {"release_frequency": None, "lead_time_days": None}


def test_change_failure_count_and_rate_when_one_bad_release():
    """AC1: two epic releases, one with a returned event after its release moment → count 1, rate 50."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    # Epic E1 releases at 2024-01-10T00:00:00Z (sprint 2024-01)
    # Epic E2 releases at 2024-01-12T00:00:00Z (sprint 2024-01)
    # E1 has a returned event at 2024-01-11T00:00:00Z (after its release moment)
    # E2 has no returned event
    t_release_e1 = datetime(2024, 1, 10, 0, 0, 0, tzinfo=UTC)
    t_release_e2 = datetime(2024, 1, 12, 0, 0, 0, tzinfo=UTC)
    t_returned_e1 = datetime(2024, 1, 11, 0, 0, 0, tzinfo=UTC)

    epic_finished = {
        "E1": [(t_release_e1, "2024-01")],
        "E2": [(t_release_e2, "2024-01")],
    }
    epic_returned = {
        "E1": [t_returned_e1],
        "E2": [],
    }

    result = calculate_change_failure_and_mttr(
        ["E1", "E2"], "2024-01", epic_finished, epic_returned
    )
    assert result["change_failure_count"] == 1
    assert result["change_failure_rate_percent"] == 50


def test_change_failure_zero_when_no_rework():
    """AC2: releases with no returned event after release moments → count 0, rate 0."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    t_release_e1 = datetime(2024, 1, 10, 0, 0, 0, tzinfo=UTC)
    t_release_e2 = datetime(2024, 1, 12, 0, 0, 0, tzinfo=UTC)

    epic_finished = {
        "E1": [(t_release_e1, "2024-01")],
        "E2": [(t_release_e2, "2024-01")],
    }
    epic_returned = {
        "E1": [],
        "E2": [],
    }

    result = calculate_change_failure_and_mttr(
        ["E1", "E2"], "2024-01", epic_finished, epic_returned
    )
    assert result["change_failure_count"] == 0
    assert result["change_failure_rate_percent"] == 0
    assert result["mean_time_to_recovery_minutes"] is None


def test_change_failure_none_when_no_epic_link():
    """AC4: no epic link → all three values are None."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    result = calculate_change_failure_and_mttr(
        None, "2024-01", {}, {}
    )
    assert result == {
        "change_failure_count": None,
        "change_failure_rate_percent": None,
        "mean_time_to_recovery_minutes": None,
    }


def test_change_failure_none_when_no_releases():
    """AC2: sprint with no releases at all → all three values are None."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    result = calculate_change_failure_and_mttr(
        [], "2024-01", {}, {}
    )
    assert result == {
        "change_failure_count": None,
        "change_failure_rate_percent": None,
        "mean_time_to_recovery_minutes": None,
    }


def test_mttr_completed_recovery():
    """AC3: a bad release whose epic re-releases in a later sprint → recovery span from returned to next release."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    # Epic E1 releases at 2024-01-10T00:00:00Z (sprint 2024-01)
    # E1 has a returned event at 2024-01-11T00:00:00Z (after its release moment)
    # E1 re-releases at 2024-01-13T00:00:00Z (sprint 2024-02)
    # Recovery span: 2024-01-13 - 2024-01-11 = 2 days = 2880 minutes
    t_release_e1 = datetime(2024, 1, 10, 0, 0, 0, tzinfo=UTC)
    t_returned_e1 = datetime(2024, 1, 11, 0, 0, 0, tzinfo=UTC)
    t_rerelease_e1 = datetime(2024, 1, 13, 0, 0, 0, tzinfo=UTC)

    epic_finished = {
        "E1": [(t_release_e1, "2024-01"), (t_rerelease_e1, "2024-02")],
    }
    epic_returned = {
        "E1": [t_returned_e1],
    }

    result = calculate_change_failure_and_mttr(
        ["E1"], "2024-01", epic_finished, epic_returned
    )
    assert result["change_failure_count"] == 1
    assert result["change_failure_rate_percent"] == 100
    assert result["mean_time_to_recovery_minutes"] == 2880


def test_mttr_none_when_no_completed_recovery():
    """AC3: a bad release whose epic never re-releases → MTTR is None (not zero)."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    # Epic E1 releases at 2024-01-10T00:00:00Z (sprint 2024-01)
    # E1 has a returned event at 2024-01-11T00:00:00Z
    # E1 never re-releases
    t_release_e1 = datetime(2024, 1, 10, 0, 0, 0, tzinfo=UTC)
    t_returned_e1 = datetime(2024, 1, 11, 0, 0, 0, tzinfo=UTC)

    epic_finished = {
        "E1": [(t_release_e1, "2024-01")],
    }
    epic_returned = {
        "E1": [t_returned_e1],
    }

    result = calculate_change_failure_and_mttr(
        ["E1"], "2024-01", epic_finished, epic_returned
    )
    assert result["change_failure_count"] == 1
    assert result["change_failure_rate_percent"] == 100
    assert result["mean_time_to_recovery_minutes"] is None


def test_mttr_mean_of_multiple_recoveries():
    """AC3: two bad releases with completed recoveries in later sprints → MTTR is the mean."""
    from sprint_metrics.dora import calculate_change_failure_and_mttr

    # Epic E1: release at 2024-01-30 (sprint 2024-01), returned at 2024-01-31,
    #   re-release at 2024-02-02 (sprint 2024-02)
    #   Recovery span: 2 days = 2880 minutes
    # Epic E2: release at 2024-01-30 (sprint 2024-01), returned at 2024-02-01,
    #   re-release at 2024-02-05 (sprint 2024-02)
    #   Recovery span: 4 days = 5760 minutes
    # Mean = (2880 + 5760) / 2 = 4320 minutes
    t1_release = datetime(2024, 1, 30, 0, 0, 0, tzinfo=UTC)
    t1_returned = datetime(2024, 1, 31, 0, 0, 0, tzinfo=UTC)
    t1_rerelease = datetime(2024, 2, 2, 0, 0, 0, tzinfo=UTC)

    t2_release = datetime(2024, 1, 30, 0, 0, 0, tzinfo=UTC)
    t2_returned = datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)
    t2_rerelease = datetime(2024, 2, 5, 0, 0, 0, tzinfo=UTC)

    epic_finished = {
        "E1": [(t1_release, "2024-01"), (t1_rerelease, "2024-02")],
        "E2": [(t2_release, "2024-01"), (t2_rerelease, "2024-02")],
    }
    epic_returned = {
        "E1": [t1_returned],
        "E2": [t2_returned],
    }

    result = calculate_change_failure_and_mttr(
        ["E1", "E2"], "2024-01", epic_finished, epic_returned
    )
    assert result["change_failure_count"] == 2
    assert result["change_failure_rate_percent"] == 100
    assert result["mean_time_to_recovery_minutes"] == 4320


def test_calculate_dora_with_rework_data_includes_new_fields():
    """The DORA block carries all five values when rework data is provided."""
    from sprint_metrics.dora import calculate_dora

    t_release = datetime(2024, 1, 30, 0, 0, 0, tzinfo=UTC)
    t_returned = datetime(2024, 1, 31, 0, 0, 0, tzinfo=UTC)
    t_rerelease = datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)

    result = calculate_dora(
        ["E1"],
        [4.0],
        sprint_label="2024-01",
        epic_finished={"E1": [(t_release, "2024-01"), (t_rerelease, "2024-02")]},
        epic_returned={"E1": [t_returned]},
    )
    assert result["release_frequency"] == 1
    assert result["lead_time_days"] == 4
    assert result["change_failure_count"] == 1
    assert result["change_failure_rate_percent"] == 100
    assert result["mean_time_to_recovery_minutes"] == 1440


def test_range_dora_description_fragment_lives_in_dora_module():
    """AC3: the dora answer's description fragment is owned by dora.py and
    tells the reader what the generated /range row tells them about dora:
    each entry carries the sprint's DORA block — its release frequency and
    lead time for changes — and a sprint whose finished events carry no
    epic link reads null for both, not zero."""
    from sprint_metrics.dora import _RANGE_DORA_DESCRIPTION
    from sprint_metrics.service import SERVICE_ENDPOINTS

    for phrase in (
        "dora block",
        "release frequency",
        "lead time for changes",
        "no epic link",
        "null for both",
        "not zero",
    ):
        assert phrase in _RANGE_DORA_DESCRIPTION, f"fragment missing {phrase!r}"
    # The generated /range row tells the reader exactly this: the fragment is
    # composed into the /range endpoint description.
    range_desc = next(desc for method, path, desc in SERVICE_ENDPOINTS if path == "/range")
    assert _RANGE_DORA_DESCRIPTION in range_desc
