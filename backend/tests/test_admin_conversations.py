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
    assert "scan_truncated" in body


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self._data = self._data[:n]
        return self

    def execute(self):
        return _FakeResult(self._data)


class _FakeClient:
    def __init__(self, data):
        self._data = data

    def table(self, name):
        return _FakeQuery(self._data)


def _fake_row(conversation_id: str, seconds: int) -> dict:
    return {
        "conversation_id": conversation_id,
        "conversation_name": None,
        "role": "visitor",
        "content": f"msg-{seconds}",
        "created_at": f"2024-01-01T00:00:{seconds:02d}Z",
        "read": True,
        "needs_attention": False,
    }


def test_list_inbox_reports_scan_truncated_when_scan_hits_the_limit(monkeypatch):
    """RECS.md: 'Admin inbox silently caps at a 3000-row scan window, no "there
    may be more" UI signal'. Mocks the Supabase client entirely so the scan limit
    can be controlled precisely, independent of real table state."""
    monkeypatch.setattr(db, "INBOX_SCAN_LIMIT", 3)
    rows = [_fake_row(f"c{i}", i) for i in range(5)]
    monkeypatch.setattr(db, "get_client", lambda: _FakeClient(rows))

    summaries, scan_truncated = db.list_inbox()
    assert scan_truncated is True
    assert len(summaries) == 3


def test_list_inbox_reports_not_truncated_when_scan_is_under_the_limit(monkeypatch):
    monkeypatch.setattr(db, "INBOX_SCAN_LIMIT", 10)
    rows = [_fake_row(f"c{i}", i) for i in range(3)]
    monkeypatch.setattr(db, "get_client", lambda: _FakeClient(rows))

    summaries, scan_truncated = db.list_inbox()
    assert scan_truncated is False
    assert len(summaries) == 3


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
