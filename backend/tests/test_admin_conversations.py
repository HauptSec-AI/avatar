"""Admin conversation CRUD: list inbox, open thread (marks read + clears attention),
post a human message, resolve without replying.
"""

import uuid

from app import db


def _seed(conversation_id: str, **kwargs) -> dict:
    payload = dict(
        conversation_id=conversation_id,
        role="visitor",
        content="Hello, I need help with something.",
    )
    payload.update(kwargs)
    return db.insert_message(**payload)


def test_list_conversations_includes_seeded_conversation(admin_client):
    conversation_id = str(uuid.uuid4())
    _seed(conversation_id, conversation_name="AB")

    resp = admin_client.get("/admin/conversations")
    assert resp.status_code == 200
    body = resp.json()
    ids = {c["conversation_id"] for c in body["conversations"]}
    assert conversation_id in ids

    summary = next(c for c in body["conversations"] if c["conversation_id"] == conversation_id)
    assert summary["conversation_name"] == "AB"
    assert summary["message_count"] == 1
    assert summary["unread"] is True


def test_open_conversation_marks_read_and_clears_attention(admin_client):
    conversation_id = str(uuid.uuid4())
    _seed(conversation_id, content="I really need to talk to a human urgently.")
    row2 = db.insert_message(
        conversation_id,
        "avatar",
        "I've flagged this for the human.",
        needs_attention=True,
    )
    assert row2["needs_attention"] is True
    assert row2["read"] is False

    resp = admin_client.post(f"/admin/conversations/{conversation_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == conversation_id
    messages = body["messages"]
    assert len(messages) == 2
    # Oldest first.
    assert messages[0]["content"] == "I really need to talk to a human urgently."
    for m in messages:
        assert m["read"] is True
        assert m["needs_attention"] is False

    # Confirm persisted, not just returned.
    persisted = db.get_conversation_messages(conversation_id)
    for m in persisted:
        assert m["read"] is True
        assert m["needs_attention"] is False


def test_open_conversation_invalid_id_returns_400(admin_client):
    resp = admin_client.post("/admin/conversations/not-a-uuid")
    assert resp.status_code == 400


def test_open_conversation_get_is_no_longer_allowed(admin_client):
    """Was a GET; switched to POST so it can't be triggered cross-site by a
    SameSite=Lax-cookied top-level navigation (CSRF that dismisses a flagged
    conversation)."""
    conversation_id = str(uuid.uuid4())
    _seed(conversation_id)
    resp = admin_client.get(f"/admin/conversations/{conversation_id}")
    assert resp.status_code == 405


def test_post_admin_message_inserts_human_row_marked_read(admin_client):
    conversation_id = str(uuid.uuid4())
    _seed(conversation_id)

    resp = admin_client.post(
        f"/admin/conversations/{conversation_id}/messages",
        json={"content": "This is the human replying."},
    )
    assert resp.status_code == 200
    message = resp.json()["message"]
    assert message["role"] == "human"
    assert message["content"] == "This is the human replying."
    assert message["read"] is True

    persisted = db.get_conversation_messages(conversation_id)
    human_rows = [m for m in persisted if m["role"] == "human"]
    assert len(human_rows) == 1
    assert human_rows[0]["read"] is True


def test_resolve_conversation_clears_needs_attention_without_reply(admin_client):
    conversation_id = str(uuid.uuid4())
    _seed(conversation_id)
    db.insert_message(
        conversation_id,
        "avatar",
        "Flagging this for the human.",
        needs_attention=True,
    )

    before = db.get_conversation_messages(conversation_id)
    assert any(m["needs_attention"] for m in before)
    message_count_before = len(before)

    resp = admin_client.post(f"/admin/conversations/{conversation_id}/resolve")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    after = db.get_conversation_messages(conversation_id)
    assert not any(m["needs_attention"] for m in after)
    # No reply was added.
    assert len(after) == message_count_before
    assert not any(m["role"] == "human" for m in after)
