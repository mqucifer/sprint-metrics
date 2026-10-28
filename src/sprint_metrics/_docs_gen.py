"""Generate marked sections for docs/ files from the code."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sprint_metrics.metrics import ALL_METRICS
from sprint_metrics.report import _METRIC_COLUMNS
from sprint_metrics.schema import (
    EVENT_INTAKE_SCHEMA,
    SPRINT_RANGE_SCHEMA,
    TREND_SCHEMA,
)
from sprint_metrics.service import SERVICE_ENDPOINTS
from sprint_metrics.thresholds import DEFAULT_THRESHOLDS


def _first_doc_line(func) -> str:
    """Return the first non-empty line of a function's docstring, stripped."""
    if func.__doc__ is None:
        return ""
    for line in func.__doc__.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _generate_metrics_content() -> str:
    """Generate the text for the 'metrics' marked section."""
    import sprint_metrics.metrics as metrics_mod

    metric_to_func = {
        "cycle_time_days": "calculate_cycle_time_and_lead_time",
        "lead_time_days": "calculate_cycle_time_and_lead_time",
        "cycle_time_minutes": "calculate_cycle_time_minutes",
        "lead_time_minutes": "calculate_lead_time_minutes",
        "throughput": "calculate_throughput",
        "wip_violations": "calculate_wip_violations",
        "blocked_aging_days": "calculate_blocked_aging",
        "first_attempt_rate_percent": "calculate_first_attempt_rate",
        "failure_breakdown": "calculate_failure_breakdown",
        "points_delivered": "calculate_points_delivered",
        "model_minutes_middle": "calculate_model_minutes_middle",
        "model_minutes_total": "calculate_model_minutes_total",
        "input_tokens_middle": "calculate_input_tokens_middle",
        "input_tokens_total": "calculate_input_tokens_total",
        "output_tokens_middle": "calculate_output_tokens_middle",
        "output_tokens_total": "calculate_output_tokens_total",
        "cached_input_percent": "calculate_cached_input_percent",
        "reasoning_output_percent": "calculate_reasoning_output_percent",
    }

    # Metrics whose description is not the first line of a single calculate
    # function's docstring (shared function, or no calculate function at all),
    # or whose table row carries a note the docstring does not.
    metric_descriptions: dict[str, str] = {
        "first_attempt_numerator": (
            "Return the count of completed cards whose attempts equals 1, as a whole count."
        ),
        "first_attempt_denominator": (
            "Return the total count of completed cards, as a whole count."
        ),
        "superseded_count": (
            "Return the count of cards marked superseded in the sprint, as a whole count. "
            "Excluded from throughput and in-flight calculations."
        ),
        "superseded_points": (
            "Return the sum of the points value on superseded cards, in whole points "
            "(0 when a superseded card carries no points value). "
            "Excluded from throughput and in-flight calculations."
        ),
        "superseded_breakdown": (
            "Return the per-reason breakdown of superseded cards, "
            "keyed by 'sponsor' and 'story_problem' with their counts. "
            "Excluded from throughput and in-flight calculations."
        ),
        "sent_backs_count": (
            "Return the count of distinct stories sent back to the Business "
            "Analyst in the sprint, or None when no returned events are stored."
        ),
        "release_frequency": (
            "Return the count of distinct epics released in the sprint "
            "(how often epics ship), as a whole count. None when no epic "
            "link is derivable."
        ),
        "dora_lead_time_days": (
            "Return the mean, in whole days from story creation to the "
            "epic's release moment, over each released story. None when no "
            "epic link is derivable."
        ),
        "change_failure_count": (
            "Return the count of the sprint's releases that came back with "
            "rework (a 'returned' event on a story of the epic after the "
            "release moment), as a whole count, shown alongside its rate. "
            "None when no epic link is derivable."
        ),
        "change_failure_rate_percent": (
            "Return the share of the sprint's releases that came back with "
            "rework, as a whole percent (the change-failure rate), shown "
            "alongside its count. None when no epic link is derivable."
        ),
        "mean_time_to_recovery_minutes": (
            "Return the mean, in whole minutes, of the completed recovery "
            "spans (from the 'returned' event to the epic's next release "
            "moment) over the sprint's bad releases that re-released. "
            "None when no epic link is derivable, or no bad release has "
            "completed a recovery."
        ),
        "working_time_minutes": (
            "Return the sprint's working-time total, in whole minutes — "
            "the sum of the crew's session windows (from a story's started "
            "row to its returned/attempt_failed/finished row, a blocked "
            "card's blocked interval not counted), per step of the "
            "story's pipeline. None when no card carries a closed session "
            "window."
        ),
        "addition_working_time_minutes": (
            "Return the sprint's working time for stories whose kind is "
            "'addition', in whole minutes. None when no stored story row "
            "in the sprint carries a kind."
        ),
        "change_working_time_minutes": (
            "Return the sprint's working time for stories whose kind is "
            "'change', in whole minutes. None when no stored story row "
            "in the sprint carries a kind."
        ),
        "model_time_split_refinement_minutes": (
            "Return the sprint's model time spent in refinement, in whole "
            "minutes — each story's refinement seconds converted to whole "
            "minutes (the model_minutes display unit) and summed over the "
            "costed stories. None when no story in the sprint carries a "
            "model-time split."
        ),
        "model_time_split_delivery_minutes": (
            "Return the sprint's model time spent in delivery, in whole "
            "minutes — each story's delivery seconds converted to whole "
            "minutes (the model_minutes display unit) and summed over the "
            "costed stories. None when no story in the sprint carries a "
            "model-time split."
        ),
        "idle_minutes": (
            "Return the sprint's idle time — the time that passed with no "
            "session running against the sprint's total registered "
            "duration — in whole minutes (the registered span minus the "
            "in-span session time, in the sprint's registered timezone; a "
            "session window clamped to the span, a rework session never "
            "re-sent as 'started' reads as idle). None where the sprint is "
            "not registered or no session ran inside the span."
        ),
    }

    display_overrides: dict[str, str] = {
        "superseded_count": "Superseded count",
    }

    lines = [
        "| Display name | Metric key | Description |",
        "|---|---|---|",
    ]
    for metric_key in sorted(ALL_METRICS):
        display_name = display_overrides.get(metric_key, _METRIC_COLUMNS.get(metric_key))
        if display_name is None:
            continue
        if metric_key in metric_descriptions:
            description = metric_descriptions[metric_key]
        else:
            func_name = metric_to_func.get(metric_key)
            if func_name is None:
                continue
            func = getattr(metrics_mod, func_name)
            description = _first_doc_line(func)
        lines.append(f"| {display_name} | `{metric_key}` | {description} |")
    return "\n".join(lines) + "\n"


def _generate_thresholds_content() -> str:
    """Generate the text for the 'thresholds' marked section."""
    lines = [
        "| Metric | Default threshold | Breach direction |",
        "|---|---|---|",
    ]
    for metric, value in DEFAULT_THRESHOLDS.items():
        if metric in ("throughput", "first_attempt_rate_percent"):
            direction = "falls below"
        else:
            direction = "exceeds"
        lines.append(f"| `{metric}` | {value} | {direction} |")
    return "\n".join(lines) + "\n"


def _generate_service_content() -> str:
    """Generate the text for the 'service' marked section."""
    lines = [
        "Long-lived HTTP service that accepts board events and answers range and trend queries from Postgres.",
        "",
        "| Method | Path | Description |",
        "|---|---|---|",
    ]
    for method, path, description in SERVICE_ENDPOINTS:
        lines.append(f"| {method} | {path} | {description} |")
    return "\n".join(lines) + "\n"


def _generate_section_content(marker_id: str) -> str:
    """Generate the marked section text for the given marker ID."""
    generators = {
        "metrics": _generate_metrics_content,
        "thresholds": _generate_thresholds_content,
        "service": _generate_service_content,
    }
    gen = generators.get(marker_id)
    if gen is None:
        raise ValueError(f"unknown marker ID: {marker_id!r}")
    return gen()


def generate_file(path: Path) -> None:
    """Replace all marked sections in the given docs file with generated content.

    If the file does not contain a BEGIN marker, writes an error to stderr
    and raises SystemExit(1). The file is left byte-identical.
    """
    text = path.read_text()
    lines = text.splitlines(keepends=True)

    markers: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if stripped.startswith("BEGIN:"):
            marker_id = stripped[len("BEGIN:") :]
            markers.append((i, marker_id))

    if not markers:
        print(f"_docs_gen: no BEGIN marker found in {path}", file=sys.stderr)
        raise SystemExit(1)

    for begin_idx, marker_id in reversed(markers):
        end_idx = None
        for i in range(begin_idx + 1, len(lines)):
            stripped = lines[i].rstrip("\r\n")
            if stripped == f"END:{marker_id}":
                end_idx = i
                break

        if end_idx is None:
            print(f"_docs_gen: no END:{marker_id} marker found in {path}", file=sys.stderr)
            raise SystemExit(1)

        content = _generate_section_content(marker_id)
        new_text = "".join(lines[: begin_idx + 1]) + content + "".join(lines[end_idx:])
        lines = new_text.splitlines(keepends=True)

    path.write_text("".join(lines))


def generate_all() -> None:
    """Regenerate all marked sections in the docs/ files and the schema files."""
    repo_root = Path(__file__).parent.parent.parent
    _generate_schema_files(repo_root / "schemas")
    for relative_path in (
        "docs/metrics.md",
        "docs/thresholds.md",
        "docs/service.md",
    ):
        path = repo_root / relative_path
        if not path.exists():
            print(f"_docs_gen: skipping {path} (does not exist)", file=sys.stderr)
            continue
        generate_file(path)


def main() -> int:
    """Entry point for python -m sprint_metrics._docs_gen."""
    try:
        generate_all()
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    return 0


def _generate_schema_files(output_dir: Path) -> None:
    """Write the three JSON Schema files to the given directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "sprint-range.json": SPRINT_RANGE_SCHEMA,
        "trend.json": TREND_SCHEMA,
        "event-intake.json": EVENT_INTAKE_SCHEMA,
    }
    for filename, schema in schemas.items():
        (output_dir / filename).write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
