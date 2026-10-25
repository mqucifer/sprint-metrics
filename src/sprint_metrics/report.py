"""Response constants for the sprint-metrics service: the api_version and metric display names."""

from __future__ import annotations

API_VERSION = "4"


_METRIC_COLUMNS: dict[str, str] = {
    "cycle_time_days": "Cycle time",
    "lead_time_days": "Lead time",
    "cycle_time_minutes": "Cycle time (min)",
    "lead_time_minutes": "Lead time (min)",
    "throughput": "Throughput",
    "points_delivered": "Points delivered",
    "wip_violations": "WIP violations",
    "blocked_aging_days": "Blocked aging",
    "first_attempt_rate_percent": "First attempt",
    "first_attempt_numerator": "First-attempt numerator",
    "first_attempt_denominator": "First-attempt denominator",
    "failure_breakdown": "Top causes",
    "superseded_count": "Superseded",
    "superseded_points": "Superseded points",
    "superseded_breakdown": "Superseded breakdown",
    "model_minutes_middle": "Model minutes (middle)",
    "model_minutes_total": "Model minutes (total)",
    "input_tokens_middle": "Input tokens (middle)",
    "input_tokens_total": "Input tokens (total)",
    "output_tokens_middle": "Output tokens (middle)",
    "output_tokens_total": "Output tokens (total)",
    "cached_input_percent": "Cached input percent",
    "reasoning_output_percent": "Reasoning output percent",
}
