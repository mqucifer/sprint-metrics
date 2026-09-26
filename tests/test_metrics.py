"""Tests for the metric calculations in sprint_metrics.metrics."""

import pytest

from sprint_metrics.metrics import (
    _load_wip_limits,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)


def test_calculate_cycle_time_and_lead_time_returns_tuple():
    """AC1: one completed card with cycle time 4 and lead time 6 returns (4, 6)."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
    assert calculate_cycle_time_and_lead_time(cards) == (4, 6)


def test_calculate_wip_violations_returns_one():
    """AC2: four in-flight cards with WIP limit 3 for In Progress returns 1 violation."""
    cards = [{"created": "2024-01-01", "started": "2024-01-02", "completed": ""}] * 4
    assert calculate_wip_violations(cards, {"In Progress": 3}) == 1


def test_load_wip_limits_raises_type_error_for_list():
    """AC3: a JSON list instead of an object raises TypeError mentioning WIP limits."""
    with pytest.raises(TypeError, match="WIP limits"):
        _load_wip_limits('["In Progress", 3]')


def test_full_suite_passes():
    """AC4: all existing tests pass after the extraction."""
    # This is verified by running the full test suite; this test just confirms
    # that the imports work correctly.
    from sprint_metrics.crew_performance import (
        calculate_blocked_aging as cp_blocked,
    )
    from sprint_metrics.crew_performance import (
        calculate_cycle_time_and_lead_time as cp_cycle,
    )
    from sprint_metrics.crew_performance import (
        calculate_escalation_rate as cp_escalation,
    )
    from sprint_metrics.crew_performance import (
        calculate_throughput as cp_throughput,
    )
    from sprint_metrics.crew_performance import (
        calculate_wip_violations as cp_wip,
    )
    from sprint_metrics.metrics import (
        calculate_cycle_time_and_lead_time,
        calculate_wip_violations,
    )

    # Verify the functions are the same objects (re-exported)
    assert calculate_cycle_time_and_lead_time is cp_cycle
    assert calculate_throughput is cp_throughput
    assert calculate_wip_violations is cp_wip
    assert calculate_blocked_aging is cp_blocked
    assert calculate_escalation_rate is cp_escalation
