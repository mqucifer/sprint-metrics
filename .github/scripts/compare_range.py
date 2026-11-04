"""The docker job's check that GET /range answers as the image before this change did.

usage: compare_range.py PREVIOUS NEW DECLARATION

Every answer the previous image gave keeps its value in this one, and nothing is added
or removed, apart from what `declared-changes.json` declares for GET /range: each
answer a change adds, changes or removes on purpose, by its JSONPath (RFC 9535). The
release empties the declaration and moves api_version once, so what's declared is
accepted for that release only (mqucifer/crew#1019). The response's api_version is
left out of the comparison, and must be the one the declaration holds.

The paths read are a subset of RFC 9535's: `$`, then steps of `.name` or `['name']`
for a member, `[n]` for an array's element, and `[*]` for every member or element.
GET /range keys its sprints by label, so `$.sprints[*].working_time` is every sprint's
working time, and `$.sprints['2024-01']` one sprint's.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

RESPONSE = "GET /range"
FILE = "declared-changes.json"
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SEGMENT = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\['([^'\\]*)'\]|\[(\*|\d+)\]")
_FIELDS = ("response", "path", "why")

# A path's steps: a member's name, an element's index, or None for every one.
Step = str | int | None


class Unreadable(ValueError):
    """The declaration isn't one, said in words the job prints."""


def steps(path: str) -> list[Step]:
    """A declared path's steps, or Unreadable for one outside the subset read."""
    found: list[Step] = []
    at = 1
    while path.startswith("$") and at < len(path):
        step = _SEGMENT.match(path, at)
        if step is None:
            break
        name, quoted, index = step.groups()
        if index is not None:
            found.append(None if index == "*" else int(index))
        else:
            found.append(name if name is not None else quoted)
        at = step.end()
    if not path.startswith("$") or at != len(path) or not found:
        raise Unreadable(
            f"{FILE} declares the path {path!r}, which this check can't read: it reads "
            "`$` followed by `.name`, `['name']`, `[n]` or `[*]` steps, such as "
            "`$.sprints[*].working_time`"
        )
    return found


def declared(text: str) -> tuple[str, list[dict[str, str]]]:
    """The declaration's api_version and its changes."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Unreadable(f"{FILE} isn't JSON: {exc}") from exc
    version = raw.get("api_version") if isinstance(raw, dict) else None
    changes = raw.get("changes") if isinstance(raw, dict) else None
    if not isinstance(version, str) or not isinstance(changes, list):
        raise Unreadable(f'{FILE} is an object with "api_version", a string, and "changes", a list')
    for change in changes:
        if not isinstance(change, dict) or not all(isinstance(change.get(f), str) for f in _FIELDS):
            raise Unreadable(
                f'each of {FILE}\'s "changes" is an object with "response", "path" and "why": '
                f"{json.dumps(change)}"
            )
    return version, changes


def without(value: Any, path: list[Step]) -> Any:
    """`value` with every node `path` reaches left out."""
    head, rest = path[0], path[1:]

    def reached(key: str | int) -> bool:
        return head is None or key == head

    if isinstance(value, dict) and not isinstance(head, int):
        if not rest:
            return {k: v for k, v in value.items() if not reached(k)}
        return {k: without(v, rest) if reached(k) else v for k, v in value.items()}
    if isinstance(value, list) and not isinstance(head, str):
        if not rest:
            return [v for i, v in enumerate(value) if not reached(i)]
        return [without(v, rest) if reached(i) else v for i, v in enumerate(value)]
    return value


def member(at: str, key: str) -> str:
    """The path to `key` under `at`, in the form a declaration takes."""
    return f"{at}.{key}" if _NAME.match(key) else f"{at}['{key}']"


def differences(prev: Any, new: Any, at: str = "$") -> Iterator[tuple[str, str]]:
    """Each (what, path) that differs: an answer changed, added or removed."""
    if isinstance(prev, dict) and isinstance(new, dict):
        for key in prev:
            if key in new:
                yield from differences(prev[key], new[key], member(at, key))
            else:
                yield "removed", member(at, key)
        yield from (("added", member(at, key)) for key in new if key not in prev)
    elif isinstance(prev, list) and isinstance(new, list):
        for i in range(min(len(prev), len(new))):
            yield from differences(prev[i], new[i], f"{at}[{i}]")
        yield from (("removed", f"{at}[{i}]") for i in range(len(new), len(prev)))
        yield from (("added", f"{at}[{i}]") for i in range(len(prev), len(new)))
    elif prev != new or isinstance(prev, bool) != isinstance(new, bool):
        yield "changed", at


def compare(prev: Any, new: Any, declaration: str) -> list[str]:
    """What's wrong, one line each, or nothing when the answers match apart from what's
    declared. Prints what the declaration accepted."""
    version, changes = declared(declaration)
    wrong: list[str] = []
    if new.get("api_version") != version:
        wrong.append(
            f'GET /range answers api_version "{new.get("api_version")}", and {FILE} holds '
            f'"{version}": the release moves both, once'
        )
    accepted = [c["path"] for c in changes if c["response"] == RESPONSE]
    prev, new = without(prev, ["api_version"]), without(new, ["api_version"])
    for path in accepted:
        found = steps(path)
        prev, new = without(prev, found), without(new, found)
    if accepted:
        print(f"Declared in {FILE}, so accepted: " + ", ".join(accepted))
    found = list(differences(prev, new))
    if found:
        wrong.append("GET /range differs from the image before this change:")
        wrong += [f"  {what}: {path}" for what, path in found]
        # An element, or a member keyed by data such as a sprint's label, is one of many.
        wildcards = sorted({re.sub(r"\[\d+\]|\['[^']*'\]", "[*]", path) for _, path in found})
        wrong.append(
            f"If that's this change's purpose, declare each in {FILE}'s changes: "
            + ", ".join(
                json.dumps({"response": RESPONSE, "path": p, "why": "..."}) for p in wildcards
            )
        )
    return wrong


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.splitlines()[2])
        return 2
    prev, new, declaration = (Path(p).read_text(encoding="utf-8") for p in argv)
    try:
        wrong = compare(json.loads(prev), json.loads(new), declaration)
    except Unreadable as exc:
        wrong = [str(exc)]
    for line in wrong:
        print(f"ERROR: {line}" if not line.startswith(" ") else line)
    if wrong:
        return 1
    print("OK: GET /range matches the image before this change, apart from what's declared")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
