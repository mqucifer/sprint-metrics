"""The per-sprint filed-split answer: how much of the sprint's filed work the crew gave itself.

The answer reports, in one object: the total the crew filed, of which found by a
role, from its own process, and split from already-filed work, beside what the
Sponsor, the operator and anyone else filed. Cards that can't be told apart
are reported as unknown and are never guessed. Null where the sprint holds no
filing facts.
"""

from __future__ import annotations


def calculate_filed_split(
    filed_events: list[tuple[str, str | None, str | None, str | None]],
) -> dict | None:
    """The sprint's filed-split answer: how much of the sprint's filed work the crew gave itself.

    ``filed_events`` is the sprint's 'filed' rows as (card_id, filer, opener,
    project) in event order; each fact is None when the crew did not send it.

    The answer carries:
    - ``crew_total``: the total cards the crew filed.
    - ``found``: crew cards where the opener is "found" (a role found a problem).
    - ``from_process``: crew cards where the opener is "process" (the crew's own process).
    - ``split``: crew cards where the opener is "split" (split from already-filed work).
    - ``unknown``: crew cards whose opener is unidentifiable or was not sent.
    - ``sponsor``: cards filed by the Sponsor.
    - ``operator``: cards filed by the operator.
    - ``other``: cards filed by anyone else, or by someone the facts cannot tell.
    - ``total_cards``: the sprint's total filed cards (all filer buckets sum).
    - ``self_filed_share``: the whole percent of the sprint's total cards that
      the crew filed, carried with its numerator and denominator.

    The buckets partition the sprint: crew_total = found + from_process + split
    + unknown, and crew_total + sponsor + operator + other = total_cards. The
    denominator is the sprint's total filed cards, including a card whose
    facts cannot tell who filed it — it was filed, it just can't be told
    apart, and no bucket is guessed for it.

    Returns ``None`` when the sprint holds no filing facts: no 'filed' rows at
    all, or 'filed' rows whose filing-fact fields are all absent. ``None`` is
    'no facts' (no data), not 'no self-filed work' — a sprint whose facts show
    the crew filed nothing reads the zero crew counts, not ``None``.
    """
    if not any(
        filer is not None or opener is not None or project is not None
        for _card_id, filer, opener, project in filed_events
    ):
        return None
    crew_total = 0
    found = 0
    from_process = 0
    split = 0
    unknown = 0
    sponsor = 0
    operator = 0
    other = 0

    for _card_id, filer, opener, _project in filed_events:
        if filer == "crew":
            crew_total += 1
            if opener == "found":
                found += 1
            elif opener == "process":
                from_process += 1
            elif opener == "split":
                split += 1
            else:
                unknown += 1
        elif filer == "sponsor":
            sponsor += 1
        elif filer == "operator":
            operator += 1
        else:
            other += 1

    total_cards = crew_total + sponsor + operator + other
    percent = round(crew_total / total_cards * 100) if total_cards > 0 else 0

    return {
        "crew_total": crew_total,
        "found": found,
        "from_process": from_process,
        "split": split,
        "unknown": unknown,
        "sponsor": sponsor,
        "operator": operator,
        "other": other,
        "total_cards": total_cards,
        "self_filed_share": {
            "percent": percent,
            "numerator": crew_total,
            "denominator": total_cards,
        },
    }


def _attach_range_filed(result: dict, labels: list[str], filed: dict[str, dict | None]) -> None:
    """Attach the filed-split answer to each range entry.

    An entry for a sprint with no events or no filing facts carries filed null,
    so pre-rollout history reads as no data, not zero. An entry for a sprint
    with filing facts carries its split, including zero crew counts when the
    crew filed nothing.
    """
    for label in labels:
        result["sprints"][label]["filed"] = filed.get(label)


_RANGE_FILED_DESCRIPTION = (
    "Each entry also carries filed: the sprint's filed-split answer — "
    "the total the crew filed (crew_total), of which found by a role "
    "(found), from its own process (from_process), and split from "
    "already-filed work (split), beside what the Sponsor (sponsor), "
    "the operator (operator) and anyone else, or with no known filer (other) filed; cards that "
    "can't be told apart are reported as unknown, never guessed. "
    "total_cards is the sprint's total filed cards; the buckets partition "
    "the sprint (crew_total = found + from_process + split + unknown, and "
    "crew_total + sponsor + operator + other = total_cards). "
    "self_filed_share carries the whole percent of the sprint's total "
    "cards that the crew filed, with its numerator (crew_total) and "
    "denominator (total_cards). "
    "A card counts in the sprint named on its 'filed' event (the sprint "
    "it was filed in), which may differ from the sprint where it merges. "
    "A sprint with events but no filing facts reads filed null "
    "(no data, not zero); a sprint with filing facts in which the crew "
    "filed nothing reads the zero crew counts. "
)
