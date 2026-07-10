"""Builds the single summarizing user prompt handed to the Agent each turn.

Per SPEC: one user prompt covers the whole three-way history (visitor / avatar /
human), rather than a user/assistant message list, since the human can also speak.
"""

from typing import Any


def build_transcript(rows: list[dict[str, Any]], owner_name: str) -> str:
    visitor_name = next(
        (r.get("conversation_name") for r in reversed(rows) if r.get("conversation_name")),
        None,
    )
    visitor_label = f"Visitor ({visitor_name})" if visitor_name else "Visitor"

    lines = []
    for row in rows:
        role = row["role"]
        if role == "visitor":
            label = visitor_label
        elif role == "avatar":
            label = "You (the Avatar)"
        elif role == "human":
            label = f"{owner_name} (the human, joined live)"
        else:
            label = role
        lines.append(f"[{label}]: {row['content']}")

    lines.append("\nRespond now as the Avatar to the Visitor's latest message above.")
    return "\n".join(lines)
