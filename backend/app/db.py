"""Supabase-backed persistence for the `messages` table.

Schema (see README.md for the full `create table` statement):
  id, conversation_id, conversation_name, role, content, tool_calls,
  needs_attention, read, created_at
"""

from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from . import config

TABLE = "messages"

# How many of the most-recent rows the admin inbox scans to build conversation
# summaries. One round trip; generous enough for a personal-site volume of traffic.
INBOX_SCAN_LIMIT = 3000


@lru_cache(maxsize=1)
def get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def insert_message(
    conversation_id: str,
    role: str,
    content: str,
    conversation_name: str | None = None,
    tool_calls: list[str] | None = None,
    needs_attention: bool = False,
    read: bool = False,
) -> dict[str, Any]:
    row = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "needs_attention": needs_attention,
        "read": read,
    }
    if conversation_name:
        row["conversation_name"] = conversation_name
    if tool_calls:
        row["tool_calls"] = tool_calls
    result = get_client().table(TABLE).insert(row).execute()
    return result.data[0]


def get_conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    result = (
        get_client()
        .table(TABLE)
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def open_conversation(conversation_id: str) -> list[dict[str, Any]]:
    """Mark every row in the thread read + attention-cleared; return the thread, oldest first."""
    result = (
        get_client()
        .table(TABLE)
        .update({"read": True, "needs_attention": False})
        .eq("conversation_id", conversation_id)
        .execute()
    )
    rows = result.data
    rows.sort(key=lambda r: r["created_at"])
    return rows


def resolve_conversation(conversation_id: str) -> None:
    get_client().table(TABLE).update({"needs_attention": False}).eq(
        "conversation_id", conversation_id
    ).eq("needs_attention", True).execute()


def list_inbox() -> list[dict[str, Any]]:
    """One round trip: scan recent rows, group into per-conversation summaries, newest first."""
    result = (
        get_client()
        .table(TABLE)
        .select("*")
        .order("created_at", desc=True)
        .limit(INBOX_SCAN_LIMIT)
        .execute()
    )
    rows = result.data

    by_conversation: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_conversation.setdefault(row["conversation_id"], []).append(row)

    summaries = []
    for conversation_id, convo_rows in by_conversation.items():
        # convo_rows are already newest-first (source query was desc).
        latest = convo_rows[0]
        name = next((r["conversation_name"] for r in convo_rows if r.get("conversation_name")), None)
        summaries.append(
            {
                "conversation_id": conversation_id,
                "conversation_name": name,
                "preview": latest["content"],
                "last_role": latest["role"],
                "last_message_at": latest["created_at"],
                "message_count": len(convo_rows),
                "unread": any(not r["read"] for r in convo_rows),
                "needs_attention": any(r["needs_attention"] for r in convo_rows),
            }
        )
    summaries.sort(key=lambda s: s["last_message_at"], reverse=True)
    return summaries
