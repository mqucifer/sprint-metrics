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
    from sprint_metrics.thresholds import calculate_flags as flags_from_thresholds

    assert Card is CardFromCard
    assert calculate_cycle_time_and_lead_time is cycle_from_metrics
    assert calculate_throughput is throughput_from_metrics
    assert calculate_wip_violations is wip_from_metrics
    assert calculate_blocked_aging is blocked_from_metrics
    assert calculate_escalation_rate is escalation_from_metrics
    assert calculate_flags is flags_from_thresholds


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


def test_scrape_server_module_is_gone():
    """AC1: importing sprint_metrics.serve raises ModuleNotFoundError."""
    import pytest

    with pytest.raises(ModuleNotFoundError):
        import sprint_metrics.serve  # noqa: F401


def test_scrape_only_loaders_and_formatter_are_gone():
    """AC2: the cards-file loader, the WIP-limits-file loader and the Prometheus
    formatter are gone."""
    import sprint_metrics
    from sprint_metrics import card, metrics, report

    assert not hasattr(card, "_load_cards")
    assert not hasattr(metrics, "_load_wip_limits")
    assert not hasattr(report, "format_prometheus_report")
    assert not hasattr(sprint_metrics, "format_prometheus_report")


def test_cli_formatters_and_loaders_are_gone():
    """AC1, AC2: the table and markdown formatters, the CLI-only sprint-range
    parser and sprints-file loader, and the thresholds-file loader are gone,
    while the names the service and the docs consume survive."""
    import sprint_metrics
    from sprint_metrics import report, sprint_range, thresholds

    for name in ("format_performance_table", "format_markdown_report"):
        assert not hasattr(report, name)
    for name in (
        "format_sprint_range_table",
        "format_sprint_range_markdown",
        "_parse_sprint_range",
        "_load_sprints",
    ):
        assert not hasattr(sprint_range, name)
    assert not hasattr(thresholds, "_load_thresholds")
    assert not hasattr(sprint_metrics, "format_performance_table")
    assert report.API_VERSION == "3"
    assert report._METRIC_COLUMNS
    assert callable(sprint_range._parse_sprint_label)
    assert callable(sprint_range.format_sprint_range_json)
    assert thresholds.DEFAULT_THRESHOLDS
    assert callable(thresholds.calculate_flags)


def test_single_sprint_formatter_and_schema_are_gone():
    """#765 AC1: the single-sprint JSON formatter and its response schema are
    gone, the package no longer re-exports the formatter, and the range and
    trend code the service uses still imports."""
    import pytest

    import sprint_metrics
    from sprint_metrics import report, schema

    with pytest.raises(ImportError):
        from sprint_metrics import format_json_report  # noqa: F401
    assert not hasattr(report, "format_json_report")
    assert "format_json_report" not in sprint_metrics.__all__
    assert not hasattr(schema, "SINGLE_SPRINT_SCHEMA")
    assert schema.SPRINT_RANGE_SCHEMA and schema.TREND_SCHEMA and schema.EVENT_INTAKE_SCHEMA
