"""Generate marked sections for docs/ files from the code."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sprint_metrics.cli import build_parser
from sprint_metrics.metrics import ALL_METRICS
from sprint_metrics.report import _METRIC_COLUMNS
from sprint_metrics.schema import SINGLE_SPRINT_SCHEMA
from sprint_metrics.serve import serve_metrics
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
        "throughput": "calculate_throughput",
        "wip_violations": "calculate_wip_violations",
        "blocked_aging_days": "calculate_blocked_aging",
        "escalation_rate_percent": "calculate_escalation_rate",
        "first_attempt_rate_percent": "calculate_first_attempt_rate",
        "failure_breakdown": "calculate_failure_breakdown",
    }

    lines = [
        "| Display name | Metric key | Description | Prometheus name |",
        "|---|---|---|---|",
    ]
    for metric_key in sorted(ALL_METRICS):
        display_name = _METRIC_COLUMNS[metric_key]
        func_name = metric_to_func[metric_key]
        func = getattr(metrics_mod, func_name)
        description = _first_doc_line(func)
        if metric_key == "failure_breakdown":
            prom_name = "sprint_failure_count"
        else:
            prom_name = f"sprint_{metric_key}"
        lines.append(f"| {display_name} | `{metric_key}` | {description} | `{prom_name}` |")
    return "\n".join(lines) + "\n"


def _generate_cli_args_content() -> str:
    """Generate the text for the 'cli-args' marked section."""
    parser = build_parser()
    lines: list[str] = []
    for action in parser._actions:
        if action.dest == "help":
            continue
        names = ", ".join(action.option_strings) if action.option_strings else action.dest
        help_text = action.help or ""
        default = action.default
        if default is None or action.default is action.SUPPRESS:
            default_str = ""
        else:
            default_str = f" (default: {default!r})"
        lines.append(f"- `{names}`: {help_text}{default_str}")
    return "\n".join(lines) + "\n"


def _generate_input_format_content() -> str:
    """Generate the text for the 'input-format' marked section."""
    lines = [
        "| Field | Required | Type | Description |",
        "|---|---|---|---|",
        "| `created` | Yes | ISO-8601 date | When the card was created |",
        "| `started` | No | ISO-8601 date | When work started on the card |",
        "| `completed` | No | ISO-8601 date | When the card was completed |",
        "| `blocked_since` | No | ISO-8601 date | When the card was blocked |",
        "| `attempts` | No | integer | Number of attempts (default: 1) |",
        "| `failure_class` | No | string | Classification of the failure |",
        "| `failure_role` | No | string | Role responsible for the failure |",
        "",
        "```json",
        json.dumps(
            [
                {
                    "created": "2024-01-03",
                    "started": "2024-01-05",
                    "completed": "2024-01-10",
                    "blocked_since": "2024-01-06",
                },
                {"created": "2024-01-04"},
            ],
            indent=2,
        ),
        "```",
    ]
    return "\n".join(lines) + "\n"


def _generate_formats_content() -> str:
    """Generate the text for the 'formats' marked section."""
    return "```json\n" + json.dumps(SINGLE_SPRINT_SCHEMA, indent=2) + "\n```\n"


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


def _generate_scrape_content() -> str:
    """Generate the text for the 'scrape' marked section."""
    doc = serve_metrics.__doc__ or ""
    lines = [
        doc.strip(),
        "",
        "Endpoints:",
        "- `/metrics` — Prometheus text exposition format",
        "- `/json` — JSON API response",
    ]
    return "\n".join(lines) + "\n"


def _generate_section_content(marker_id: str) -> str:
    """Generate the marked section text for the given marker ID."""
    generators = {
        "metrics": _generate_metrics_content,
        "cli-args": _generate_cli_args_content,
        "input-format": _generate_input_format_content,
        "formats": _generate_formats_content,
        "thresholds": _generate_thresholds_content,
        "scrape": _generate_scrape_content,
    }
    gen = generators.get(marker_id)
    if gen is None:
        raise ValueError(f"unknown marker ID: {marker_id!r}")
    return gen()


def generate_file(path: Path) -> None:
    """Replace the marked section in the given docs file with generated content.

    If the file does not contain a BEGIN marker, writes an error to stderr
    and raises SystemExit(1). The file is left byte-identical.
    """
    text = path.read_text()
    lines = text.splitlines(keepends=True)

    begin_idx = None
    marker_id = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if stripped.startswith("BEGIN:"):
            begin_idx = i
            marker_id = stripped[len("BEGIN:") :]
            break

    if begin_idx is None:
        print(f"_docs_gen: no BEGIN marker found in {path}", file=sys.stderr)
        raise SystemExit(1)

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
    path.write_text(new_text)


def generate_all() -> None:
    """Regenerate all marked sections in the docs/ files."""
    repo_root = Path(__file__).parent.parent.parent
    for relative_path in (
        "docs/usage.md",
        "docs/cards.md",
        "docs/metrics.md",
        "docs/formats.md",
        "docs/thresholds.md",
        "docs/scrape.md",
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


if __name__ == "__main__":
    sys.exit(main())
