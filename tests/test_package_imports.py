"""Tests that the package-level imports resolve to the owning modules."""


def test_package_imports_resolve_to_owning_modules():
    """AC1: importing the public API from sprint_metrics yields the same objects
    as importing them from their owning modules."""
    from sprint_metrics import (
        Card,
        calculate_blocked_aging,
        calculate_cycle_time_and_lead_time,
        calculate_escalation_rate,
        calculate_flags,
        calculate_throughput,
        calculate_wip_violations,
        format_json_report,
        format_performance_table,
        format_prometheus_report,
    )
    from sprint_metrics.card import Card as CardFromCard
    from sprint_metrics.metrics import (
        calculate_blocked_aging as blocked_from_metrics,
    )
    from sprint_metrics.metrics import (
        calculate_cycle_time_and_lead_time as cycle_from_metrics,
    )
    from sprint_metrics.metrics import (
        calculate_escalation_rate as escalation_from_metrics,
    )
    from sprint_metrics.metrics import (
        calculate_throughput as throughput_from_metrics,
    )
    from sprint_metrics.metrics import (
        calculate_wip_violations as wip_from_metrics,
    )
    from sprint_metrics.report import (
        format_json_report as json_from_report,
    )
    from sprint_metrics.report import (
        format_performance_table as table_from_report,
    )
    from sprint_metrics.report import (
        format_prometheus_report as prom_from_report,
    )
    from sprint_metrics.thresholds import calculate_flags as flags_from_thresholds

    assert Card is CardFromCard
    assert calculate_cycle_time_and_lead_time is cycle_from_metrics
    assert calculate_throughput is throughput_from_metrics
    assert calculate_wip_violations is wip_from_metrics
    assert calculate_blocked_aging is blocked_from_metrics
    assert calculate_escalation_rate is escalation_from_metrics
    assert calculate_flags is flags_from_thresholds
    assert format_performance_table is table_from_report
    assert format_json_report is json_from_report
    assert format_prometheus_report is prom_from_report


def test_crew_performance_module_is_gone():
    """AC3: importing sprint_metrics.crew_performance raises ModuleNotFoundError."""
    import pytest

    with pytest.raises(ModuleNotFoundError):
        import sprint_metrics.crew_performance  # noqa: F401


def test_cli_module_is_gone():
    """AC6: importing sprint_metrics.cli raises ModuleNotFoundError, and the
    package no longer exports main."""
    import pytest

    import sprint_metrics

    with pytest.raises(ModuleNotFoundError):
        import sprint_metrics.cli  # noqa: F401
    assert not hasattr(sprint_metrics, "main")
    assert "main" not in sprint_metrics.__all__
