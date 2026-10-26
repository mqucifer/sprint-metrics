"""The sprint's rework answer: its send-backs to refinement and its review/QA returns, each labeled and grouped by step.

A send-back is a story handed back to the Business Analyst — a 'returned'
event. A review/QA return is a story bounced at review or QA — an
'attempt_failed' event (or, in the legacy case, a finished card with
attempts greater than 1). The answer names each story once per kind, out
of the stories started the sprint, each return carrying the step it was
returned from and the cause, both as the crew sent them on the event.
"""

from __future__ import annotations

from collections.abc import Iterable


def _group_by_story(
    returns: list[tuple[str, str | None, str | None]], inner_key: str
) -> list[dict] | None:
    """Group returns by story (card_id), preserving event order.

    ``returns`` is a list of (card_id, step, reason) tuples. ``inner_key``
    is the key under which each story's returns are listed. Returns None
    when the list is empty.
    """
    by_story: dict[str, list[dict[str, str | None]]] = {}
    for card_id, step, reason in returns:
        by_story.setdefault(card_id, []).append({"step": step, "reason": reason})
    if not by_story:
        return None
    return [{"card_id": card_id, inner_key: entries} for card_id, entries in by_story.items()]


def _by_step(returns: list[tuple[str, str | None, str | None]]) -> dict[str, int]:
    """Count returns per step (the failure_role).

    A step that was not sent on the event is counted under the empty string.
    """
    counts: dict[str, int] = {}
    for _, step, _ in returns:
        key = step or ""
        counts[key] = counts.get(key, 0) + 1
    return counts


def extract_qa_returns(cards: Iterable) -> list[tuple[str, str | None, str | None]]:
    """Extract the review/QA returns as (card_id, step, reason) tuples from Card objects.

    Only completed cards contribute. step is the failure_role (the returning
    role) and reason the failure_class (the cause), each as sent on the
    event and each None when the crew did not send it. Uses the same
    (failure class, returning role) values as the failure_breakdown.
    """
    from sprint_metrics.card import _as_cards

    results: list[tuple[str, str | None, str | None]] = []
    for card in _as_cards(cards):
        if not card.is_completed:
            continue
        if card.failures is not None and len(card.failures) > 0:
            for fc, fr in card.failures:
                results.append((card.card_id or "", fr or None, fc or None))
        elif card.attempts > 1:
            results.append((card.card_id or "", card.failure_role or None, card.failure_class or None))
    return results


def calculate_rework(
    started: int,
    returned: list[tuple[str, str | None, str | None]],
    qa_returns: list[tuple[str, str | None, str | None]] | None = None,
) -> dict:
    """The sprint's rework answer: its send-backs to refinement and its review/QA returns, each labeled and grouped by step.

    ``started`` is the count of distinct stories with a 'started' event in
    the sprint. ``returned`` is the sprint's 'returned' rows as (card_id,
    step, reason) in event order; step is the role that sent the story back
    and reason the reason for the send-back, each as sent on the event and
    each None when the crew did not send it. ``qa_returns`` is the sprint's
    review/QA returns as (card_id, step, reason) in event order; step is the
    returning role and reason the cause, using the same (failure class,
    returning role) values as the failure_breakdown. When ``qa_returns`` is
    None the answer carries only the send-backs part.

    Each story is named once per kind, its returns in event order.
    ``sent_backs`` is None when the sprint holds no 'returned' events, and
    ``qa_returns`` is None when the sprint holds no review/QA returns, so
    pre-rollout history reads as no data, not zero. ``by_step`` groups each
    part's returns by step (the count per step), present when ``qa_returns``
    is given and at least one part has data. A 'returned' event completes no
    story and changes no other measure.
    """
    sent_backs = _group_by_story(returned, "send_backs")
    result: dict = {
        "started": started,
        "sent_backs": sent_backs,
    }
    if qa_returns is not None:
        result["qa_returns"] = _group_by_story(qa_returns, "returns")
        by_step: dict[str, dict[str, int]] = {}
        if sent_backs is not None:
            by_step["sent_backs"] = _by_step(returned)
        if result["qa_returns"] is not None:
            by_step["qa_returns"] = _by_step(qa_returns)
        if by_step:
            result["by_step"] = by_step
    return result
