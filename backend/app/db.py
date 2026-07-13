"""Supabase-backed persistence for the `messages` table.

Schema (see README.md for the full `create table` statement):
  id, conversation_id, conversation_name, role, content, tool_calls,
  needs_attention, read, channel, created_at

`voice_sessions` (see SPEC-VOICE.md) maps an ElevenLabs conversation onto our own
conversation_id, so tool webhooks and the post-call transcript webhook -- both of
which only know ElevenLabs' id -- can find the right thread and update it exactly once.
"""

from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from . import config

TABLE = "messages"
VOICE_SESSIONS_TABLE = "voice_sessions"

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
    channel: str = "text",
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
    # Only sent when non-default, so this stays backward-compatible with a database
    # that hasn't run the `channel` migration yet (see SPEC-VOICE.md) -- omitting the
    # key is valid against both the old schema and the new column's own default.
    if channel != "text":
        row["channel"] = channel
    result = get_client().table(TABLE).insert(row).execute()
    return result.data[0]


def set_needs_attention(message_id: int) -> None:
    get_client().table(TABLE).update({"needs_attention": True}).eq("id", message_id).execute()


def health_check() -> None:
    """Cheapest possible real round-trip to Supabase -- raises if unreachable or
    misconfigured. Used by /api/health so the Fly health check catches a DB outage
    instead of only confirming the process is alive."""
    get_client().table(TABLE).select("id").limit(1).execute()


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


def list_inbox() -> tuple[list[dict[str, Any]], bool]:
    """One round trip: scan recent rows, group into per-conversation summaries, newest first.

    Returns (summaries, scan_truncated). scan_truncated is True when the scan
    returned exactly INBOX_SCAN_LIMIT rows -- i.e. there may be older
    conversations (or older activity on a conversation whose only rows are
    past the cutoff) that this scan never saw, so the inbox could be
    incomplete rather than exhaustive.
    """
    result = (
        get_client()
        .table(TABLE)
        .select("*")
        .order("created_at", desc=True)
        .limit(INBOX_SCAN_LIMIT)
        .execute()
    )
    rows = result.data
    scan_truncated = len(rows) >= INBOX_SCAN_LIMIT

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
    return summaries, scan_truncated


# ---------------------------------------------------------------------------
# Voice (SPEC-VOICE.md): mapping ElevenLabs' own conversation id onto ours.
# ---------------------------------------------------------------------------


def record_voice_session(elevenlabs_conversation_id: str, conversation_id: str) -> None:
    """Record the pairing right after the browser connects, before any spoken turn.

    Upsert (not insert): the frontend may retry this call, or a reconnect could
    reuse the same ElevenLabs conversation_id; either way the pairing is idempotent.
    """
    get_client().table(VOICE_SESSIONS_TABLE).upsert(
        {"elevenlabs_conversation_id": elevenlabs_conversation_id, "conversation_id": conversation_id}
    ).execute()


def get_conversation_id_for_voice_session(elevenlabs_conversation_id: str) -> str | None:
    result = (
        get_client()
        .table(VOICE_SESSIONS_TABLE)
        .select("conversation_id")
        .eq("elevenlabs_conversation_id", elevenlabs_conversation_id)
        .limit(1)
        .execute()
    )
    return result.data[0]["conversation_id"] if result.data else None


def mark_push_tool_used(conversation_id: str) -> None:
    """Record that push_tool fired live during this call.

    The Pushover ping itself already went out in real time (same as text chat);
    this just makes sure the conversation's needs_attention flag gets set once the
    transcript is written, without needing a synthetic row that would otherwise
    show up *before* the visitor turns that actually caused the flag.

    Keyed by our own conversation_id (not ElevenLabs') because that's what the tool
    webhook has -- see VoicePushToolRequest. Scoped to transcript_saved=false so it
    lands on the currently in-progress call's row, not an already-claimed past one.
    """
    get_client().table(VOICE_SESSIONS_TABLE).update({"push_tool_used": True}).eq(
        "conversation_id", conversation_id
    ).eq("transcript_saved", False).execute()


def flag_latest_message_if_any(conversation_id: str) -> None:
    """Best-effort LIVE needs_attention flag for a voice call, per SPEC-VOICE.md
    ("the moment push_tool fires mid-call, ... needs_attention immediately"): sets
    it on the most recent existing row for this conversation, if there is one --
    e.g. the visitor texted before switching to voice, or a prior voice call in
    this same thread already wrote its transcript. If this call is the very first
    turn ever in this conversation, there's no row yet to flag; the post-call
    webhook's claim-based flagging (mark_push_tool_used + claim_transcript_write)
    still covers that case once the transcript lands. Pushover itself already
    fired live regardless, via the same call site as this function."""
    result = (
        get_client()
        .table(TABLE)
        .select("id")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        set_needs_attention(result.data[0]["id"])


def claim_transcript_write(elevenlabs_conversation_id: str) -> dict[str, Any] | None:
    """Atomically claim the right to write this call's transcript, exactly once.

    The post-call webhook delivers the *complete* transcript (not deltas), and
    ElevenLabs may redeliver it. This flips transcript_saved False -> True and
    returns {"conversation_id", "push_tool_used"} only for the caller that wins the
    race; a redelivery (or a concurrent duplicate) finds transcript_saved already
    True and gets None back, so it skips the insert instead of duplicating rows.
    """
    result = (
        get_client()
        .table(VOICE_SESSIONS_TABLE)
        .update({"transcript_saved": True})
        .eq("elevenlabs_conversation_id", elevenlabs_conversation_id)
        .eq("transcript_saved", False)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return {"conversation_id": row["conversation_id"], "push_tool_used": row["push_tool_used"]}


def release_transcript_claim(elevenlabs_conversation_id: str) -> None:
    """Undo claim_transcript_write after a failed transcript write, so a webhook
    redelivery gets to retry instead of finding transcript_saved permanently True
    and silently skipping the rest of the transcript forever. Guarded by
    `.eq("transcript_saved", True)` so this only ever reverts a claim this same
    call flow made, never a concurrent winner's."""
    get_client().table(VOICE_SESSIONS_TABLE).update({"transcript_saved": False}).eq(
        "elevenlabs_conversation_id", elevenlabs_conversation_id
    ).eq("transcript_saved", True).execute()


def get_existing_voice_turns(conversation_id: str) -> dict[tuple[str, str], int]:
    """(role, content) -> message id for every voice-channel row already saved for
    this conversation. Makes a retried transcript webhook idempotent per turn
    (not just per call): a redelivery that follows a partial failure re-inserts
    only the turns that never made it in, instead of duplicating ones that did."""
    result = (
        get_client()
        .table(TABLE)
        .select("id,role,content")
        .eq("conversation_id", conversation_id)
        .eq("channel", "voice")
        .execute()
    )
    return {(row["role"], row["content"]): row["id"] for row in result.data}
