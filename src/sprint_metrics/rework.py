"""The sprint's rework answer: its send-backs to refinement, out of its started stories.

A send-back is a story handed back to the Business Analyst — a 'returned'
event. The answer names each sent-back story once, out of the stories started
the sprint, each send-back carrying the step it was sent back from and the
reason, both as the crew sent them on the event.
"""

from __future__ import annotations


def calculate_rework(started: int, returned: list[tuple[str, str | None, str | None]]) -> dict:
    """The sprint's rework answer: its send-backs to refinement, out of its started stories.

    ``started`` is the count of distinct stories with a 'started' event in the
    sprint. ``returned`` is the sprint's 'returned' rows as (card_id, step,
    reason) in event order; step is the role that sent the story back and
    reason the reason for the send-back, each as sent on the event and each
    None when the crew did not send it.

    Each story is named once, its send-backs in event order. ``sent_backs`` is
    None when the sprint holds no 'returned' events, so pre-rollout history
    reads as no data, not zero send-backs. A 'returned' event completes no
    story and changes no other measure.
    """
    by_story: dict[str, list[dict[str, str | None]]] = {}
    for card_id, step, reason in returned:
        by_story.setdefault(card_id, []).append({"step": step, "reason": reason})
    sent_backs = (
        [{"card_id": card_id, "send_backs": send_backs} for card_id, send_backs in by_story.items()]
        if by_story
        else None
    )
    return {"started": started, "sent_backs": sent_backs}
