"""Command-line entry point for sprint-metrics.

This module owns ``main`` and is the target of both the ``sprint-metrics``
console script and ``python -m sprint_metrics``. It re-exports ``main`` from
``crew_performance`` so that the module split can proceed without changing the
public API.
"""

from sprint_metrics.crew_performance import main

__all__ = ["main"]
