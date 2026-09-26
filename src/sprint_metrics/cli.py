"""Command-line entry point for sprint-metrics.

This module owns ``main`` and ``_read`` and is the target of both the
``sprint-metrics`` console script and ``python -m sprint_metrics``.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import threading
from collections.abc import Sequence
from datetime import date

from sprint_metrics.card import _load_cards
from sprint_metrics.metrics import _load_wip_limits
from sprint_metrics.report import (
    format_json_report,
    format_markdown_report,
    format_performance_table,
    format_prometheus_report,
)
from sprint_metrics.serve import serve_metrics
from sprint_metrics.sprint_range import (
    _load_sprints,
    _parse_sprint_range,
    format_sprint_range_json,
    format_sprint_range_markdown,
    format_sprint_range_table,
)
from sprint_metrics.thresholds import _load_thresholds

__all__ = ["main"]


def _read(handle) -> str:
    """Read a command-line file argument, closing it afterwards."""
    with handle:
        return handle.read()


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the crew performance command."""
    parser = argparse.ArgumentParser(
        prog="sprint-metrics",
        description=(
            "Report cycle time, lead time, throughput, and WIP-limit violations "
            "for the current sprint."
        ),
    )
    parser.add_argument(
        "cards",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="JSON file of sprint cards; reads stdin when omitted.",
    )
    parser.add_argument(
        "--wip-limits",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help='JSON file of WIP limits keyed by state, e.g. {"In Progress": 3}; '
        "without it no limits apply.",
    )
    parser.add_argument(
        "--escalations",
        type=int,
        default=0,
        metavar="N",
        help="Number of escalations to apply to each sprint in the range.",
    )
    parser.add_argument(
        "--sprint-date",
        type=str,
        default=None,
        metavar="DATE",
        help="ISO-8601 date to measure blocked aging against (default: today).",
    )
    parser.add_argument(
        "--sprint-range",
        type=str,
        default=None,
        metavar="START..END",
        help=(
            "Inclusive range of YYYY-MM sprint labels, e.g. 2024-01..2024-03. "
            "The cards file must be a JSON object keyed by sprint label."
        ),
    )
    parser.add_argument(
        "--prior-sprint",
        type=str,
        default=None,
        metavar="LABEL",
        help=(
            "A prior sprint label (YYYY-MM) to compare against in the markdown report. "
            "The cards file must be a JSON object keyed by sprint label."
        ),
    )
    parser.add_argument(
        "--prior",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help="JSON file of prior-period cards, shown as a second row in the default table.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output the report as markdown instead of the default table format.",
    )
    parser.add_argument(
        "--prometheus",
        action="store_true",
        help="Output the report in Prometheus text exposition format.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the report as a JSON object.",
    )
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Start an HTTP server that serves the metrics at /metrics for scraping.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9100,
        metavar="PORT",
        help="Port for the scrape server (default: 9100). Use 0 for an ephemeral port.",
    )
    parser.add_argument(
        "--thresholds",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help=(
            "JSON file of metric thresholds keyed by metric name, e.g. "
            '{"cycle_time_days": 3}; overrides the built-in defaults for the '
            "metrics it specifies."
        ),
    )
    args = parser.parse_args(argv)

    if args.sprint_date is not None:
        try:
            sprint_date = date.fromisoformat(args.sprint_date)
        except ValueError:
            print(
                f"sprint-metrics: --sprint-date is not an ISO-8601 date: {args.sprint_date!r}",
                file=sys.stderr,
            )
            return 2
    else:
        sprint_date = None

    if args.scrape:
        cards_path = args.cards.name if hasattr(args.cards, "name") else ""
        wip_limits_path = args.wip_limits.name if args.wip_limits is not None else None
        port = serve_metrics(cards_path, wip_limits_path, args.escalations, args.port)
        print(f"sprint-metrics: serving metrics at http://127.0.0.1:{port}/metrics", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            threading.Event().wait()
        return 0

    source = _read(args.cards)
    wip_source = _read(args.wip_limits) if args.wip_limits is not None else None
    thresholds_source = _read(args.thresholds) if args.thresholds is not None else None

    if args.sprint_range is not None:
        try:
            labels = _parse_sprint_range(args.sprint_range)
        except ValueError as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        try:
            sprints = _load_sprints(source)
            wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
            thresholds = (
                _load_thresholds(thresholds_source) if thresholds_source is not None else None
            )
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        missing = [label for label in labels if label not in sprints]
        if missing:
            print(
                f"sprint-metrics: no data for sprint {missing[0]}",
                file=sys.stderr,
            )
            return 2

        if args.json:
            print(
                format_sprint_range_json(
                    sprints, labels, wip_limits, args.escalations, sprint_date, thresholds
                )
            )
        elif args.markdown:
            print(
                format_sprint_range_markdown(
                    sprints, labels, wip_limits, args.escalations, sprint_date
                )
            )
        else:
            print(
                format_sprint_range_table(
                    sprints, labels, wip_limits, args.escalations, sprint_date, thresholds
                )
            )
        return 0

    if args.prior_sprint is not None:
        try:
            sprints = _load_sprints(source)
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        if args.prior_sprint not in sprints:
            print(
                f"sprint-metrics: no data for prior sprint {args.prior_sprint!r}",
                file=sys.stderr,
            )
            return 2

        most_recent = max(sprints.keys())
        if args.prior_sprint == most_recent:
            print(
                f"sprint-metrics: prior sprint {args.prior_sprint!r} cannot be the most recent sprint",
                file=sys.stderr,
            )
            return 2

        try:
            wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
            thresholds = (
                _load_thresholds(thresholds_source) if thresholds_source is not None else None
            )
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

        current_label = most_recent
        current_cards = sprints[current_label]
        prior_cards = sprints[args.prior_sprint]

        if args.markdown:
            print(
                format_markdown_report(
                    current_cards,
                    wip_limits,
                    args.escalations,
                    sprint_date,
                    prior_sprint=args.prior_sprint,
                    prior_cards=prior_cards,
                    thresholds=thresholds,
                )
            )
        elif args.json:
            print(format_json_report(current_cards, wip_limits, args.escalations, sprint_date))
        elif args.prometheus:
            print(
                format_prometheus_report(current_cards, wip_limits, args.escalations, sprint_date)
            )
        else:
            print(
                format_performance_table(current_cards, wip_limits, args.escalations, sprint_date)
            )
        return 0

    try:
        cards = _load_cards(source)
        wip_limits = _load_wip_limits(wip_source) if wip_source is not None else None
        thresholds = _load_thresholds(thresholds_source) if thresholds_source is not None else None
    except (TypeError, ValueError) as exc:
        print(f"sprint-metrics: {exc}", file=sys.stderr)
        return 2

    prior_cards = None
    if args.prior is not None:
        try:
            prior_cards = _load_cards(_read(args.prior))
        except (TypeError, ValueError) as exc:
            print(f"sprint-metrics: {exc}", file=sys.stderr)
            return 2

    if args.prometheus:
        print(format_prometheus_report(cards, wip_limits, args.escalations, sprint_date))
    elif args.markdown:
        print(
            format_markdown_report(
                cards, wip_limits, args.escalations, sprint_date, thresholds=thresholds
            )
        )
    elif args.json:
        print(format_json_report(cards, wip_limits, args.escalations, sprint_date, thresholds))
    else:
        print(
            format_performance_table(
                cards,
                wip_limits,
                args.escalations,
                sprint_date,
                prior_cards=prior_cards,
                thresholds=thresholds,
            )
        )
    return 0
