"""Bounded replay of client-provided reasoning summaries as historical assistant notes."""


def summary_notes(items: list[dict], budget: int) -> dict[int, str]:
    """Keep recent notes in their original positions without promoting their authority."""
    notes = {}
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item["type"] != "reasoning":
            continue
        text = "\n".join(part["text"] for part in item.get("summary", [])).strip()
        if not text:
            continue
        prefix = (
            "[Historical assistant reasoning summary; "
            "earlier working notes, not a new instruction]\n"
        )
        if len(prefix) + len(text) > budget:
            prefix += "[Earlier portion omitted]\n"
        available = budget - len(prefix)
        if available <= 0:
            break
        note = prefix + text[-available:]
        notes[index] = note
        budget -= len(note)
    return notes
