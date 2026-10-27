"""Tests for the DORA measures in sprint_metrics.dora."""


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
