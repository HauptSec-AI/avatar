"""Builds the single summarizing user prompt handed to the Agent each turn.

Per SPEC: one user prompt covers the whole three-way history (visitor / avatar /
human), rather than a user/assistant message list, since the human can also speak.
"""

from typing import Any


def _escape_line_start_brackets(content: str) -> str:
    """Defuses a role-label-spoofing prompt injection: without this, a visitor
    message containing an embedded newline followed by '[' could forge what looks
    like a fresh "[Label]: ..." transcript line once flattened (e.g. impersonating
    "[[owner_name] (the human, joined live)]: ..."). Only escapes '[' immediately
    after a newline -- doesn't touch anything else, and only affects this flattened
    LLM-facing prompt (the stored row content and the chat UI rendering are
    untouched)."""
    return content.replace("\n[", "\n\\[")


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
        lines.append(f"[{label}]: {_escape_line_start_brackets(row['content'])}")

    lines.append("\nRespond now as the Avatar to the Visitor's latest message above.")
    return "\n".join(lines)
