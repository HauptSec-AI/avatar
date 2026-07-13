"""Tests for the voice API (SPEC-VOICE.md).

Split deliberately: most tests here monkeypatch the db.* voice-mapping calls so
they run against *any* environment, including one where the `channel` column and
`voice_sessions` table don't exist yet -- only the tests marked `voice_live` need
the real migration applied (run with `-m voice_live` once it's been run, or omit
`-m "not voice_live"` to include them in a full pass). This mirrors the project's
existing `llm` marker for tests that need something beyond default setup.
"""

import hashlib
import hmac
import json
import time
import uuid

import pytest
import requests

from app import agent_runner, config, db, knowledge, security, voice


# ---------------------------------------------------------------------------
# voice.py unit tests -- no HTTP, no DB.
# ---------------------------------------------------------------------------


def _sign(secret: str, ts: int, body: bytes) -> str:
    signed_payload = f"{ts}.{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v0={digest}"


def test_verify_webhook_signature_valid(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "test-secret")
    body = b'{"type": "post_call_transcription"}'
    header = _sign("test-secret", int(time.time()), body)
    assert voice.verify_webhook_signature(body, header) is True


def test_verify_webhook_signature_wrong_secret(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "test-secret")
    body = b'{"type": "post_call_transcription"}'
    header = _sign("wrong-secret", int(time.time()), body)
    assert voice.verify_webhook_signature(body, header) is False


def test_verify_webhook_signature_stale_timestamp(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "test-secret")
    body = b'{"type": "post_call_transcription"}'
    stale_ts = int(time.time()) - voice.WEBHOOK_SIGNATURE_TOLERANCE_SECONDS - 60
    header = _sign("test-secret", stale_ts, body)
    assert voice.verify_webhook_signature(body, header) is False


def test_verify_webhook_signature_missing_header(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "test-secret")
    assert voice.verify_webhook_signature(b"{}", None) is False


def test_verify_webhook_signature_malformed_header(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "test-secret")
    assert voice.verify_webhook_signature(b"{}", "not-the-right-format") is False


def test_verify_webhook_signature_no_secret_configured(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "")
    header = _sign("anything", int(time.time()), b"{}")
    assert voice.verify_webhook_signature(b"{}", header) is False


def test_build_agent_config_shape(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "voice-123")
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    monkeypatch.setattr(config, "ELEVENLABS_LLM", "gpt-4o-mini")
    knowledge.build_instructions.cache_clear()

    cfg = voice.build_agent_config("https://example.fly.dev")

    agent_cfg = cfg["conversation_config"]["agent"]
    prompt_cfg = agent_cfg["prompt"]
    assert config.OWNER_NAME in prompt_cfg["prompt"]
    assert "Markdown" in prompt_cfg["prompt"]  # voice-mode formatting addendum present
    assert config.OWNER_NAME.split(" ")[0] in agent_cfg["first_message"]
    assert prompt_cfg["llm"] == "gpt-4o-mini"
    assert cfg["conversation_config"]["tts"]["voice_id"] == "voice-123"

    tool_names = {t["name"] for t in prompt_cfg["tools"]}
    assert tool_names == {"faq_tool", "push_tool"}
    for tool in prompt_cfg["tools"]:
        assert tool["api_schema"]["url"].startswith("https://example.fly.dev/api/voice/")
        assert tool["api_schema"]["request_headers"]["Authorization"] == "Bearer shh"


# ---------------------------------------------------------------------------
# /api/voice/session -- credential minting, validation, rate limiting.
# ---------------------------------------------------------------------------


def test_voice_session_invalid_conversation_id_returns_400(client):
    resp = client.post("/api/voice/session", json={"conversation_id": "not-a-uuid"})
    assert resp.status_code == 400


def test_voice_session_returns_503_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_AGENT_ID", "")
    resp = client.post("/api/voice/session", json={"conversation_id": str(uuid.uuid4())})
    assert resp.status_code == 503


def test_voice_session_rate_limited_after_five_calls(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_AGENT_ID", "")
    conversation_id = str(uuid.uuid4())
    for _ in range(5):
        resp = client.post("/api/voice/session", json={"conversation_id": conversation_id})
        assert resp.status_code == 503  # not configured, but rate limiter still counted it

    resp = client.post("/api/voice/session", json={"conversation_id": conversation_id})
    assert resp.status_code == 429
    assert "quickly" in resp.json()["error"].lower()


def test_voice_session_mints_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(config, "ELEVENLABS_AGENT_ID", "agent-123")
    monkeypatch.setattr(voice, "mint_conversation_token", lambda: "fake-token")

    conversation_id = str(uuid.uuid4())
    resp = client.post("/api/voice/session", json={"conversation_id": conversation_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == "fake-token"
    assert body["agent_id"] == "agent-123"
    assert body["max_session_seconds"] == config.VOICE_MAX_SESSION_SECONDS
    assert security.verify_voice_session_nonce(body["session_nonce"], conversation_id)


def test_voice_session_returns_502_on_elevenlabs_error(client, monkeypatch):
    """An ElevenLabs API failure (bad key, outage, etc.) is a clean 502, not a raw 500."""
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(config, "ELEVENLABS_AGENT_ID", "agent-123")

    def _boom():
        raise requests.exceptions.HTTPError("401 Client Error")

    monkeypatch.setattr(voice, "mint_conversation_token", _boom)

    resp = client.post("/api/voice/session", json={"conversation_id": str(uuid.uuid4())})
    assert resp.status_code == 502
    assert "try again" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /api/voice/session/started -- nonce required, rate limited (RECS.md:
# "Voice session-mapping hijack" -- this endpoint used to be unauthenticated).
# ---------------------------------------------------------------------------


def test_voice_session_started_rejects_missing_nonce(client):
    resp = client.post(
        "/api/voice/session/started",
        json={"conversation_id": str(uuid.uuid4()), "elevenlabs_conversation_id": "el-x"},
    )
    assert resp.status_code == 422  # session_nonce is a required field


def test_voice_session_started_rejects_nonce_for_a_different_conversation_id(client, monkeypatch):
    """The core hijack this closes: an attacker can't bind a victim's conversation_id
    using a nonce minted for their own (real) conversation_id."""
    monkeypatch.setattr(db, "record_voice_session", lambda *a, **k: pytest.fail("must not record"))
    attacker_nonce = security.mint_voice_session_nonce(str(uuid.uuid4()))
    victim_conversation_id = str(uuid.uuid4())
    resp = client.post(
        "/api/voice/session/started",
        json={
            "conversation_id": victim_conversation_id,
            "elevenlabs_conversation_id": "el-attacker-call",
            "session_nonce": attacker_nonce,
        },
    )
    assert resp.status_code == 401


def test_voice_session_started_rejects_garbage_nonce(client):
    resp = client.post(
        "/api/voice/session/started",
        json={
            "conversation_id": str(uuid.uuid4()),
            "elevenlabs_conversation_id": "el-x",
            "session_nonce": "not-a-real-token",
        },
    )
    assert resp.status_code == 401


def test_voice_session_started_accepts_matching_nonce(client, monkeypatch):
    recorded = {}
    monkeypatch.setattr(
        db,
        "record_voice_session",
        lambda eid, cid: recorded.update({"elevenlabs_conversation_id": eid, "conversation_id": cid}),
    )
    conversation_id = str(uuid.uuid4())
    nonce = security.mint_voice_session_nonce(conversation_id)
    resp = client.post(
        "/api/voice/session/started",
        json={
            "conversation_id": conversation_id,
            "elevenlabs_conversation_id": "el-real-call",
            "session_nonce": nonce,
        },
    )
    assert resp.status_code == 200
    assert recorded == {"elevenlabs_conversation_id": "el-real-call", "conversation_id": conversation_id}


def test_voice_session_started_rate_limited_after_ten_calls(client, monkeypatch):
    monkeypatch.setattr(db, "record_voice_session", lambda *a, **k: None)
    conversation_id = str(uuid.uuid4())
    nonce = security.mint_voice_session_nonce(conversation_id)
    for _ in range(10):
        resp = client.post(
            "/api/voice/session/started",
            json={
                "conversation_id": conversation_id,
                "elevenlabs_conversation_id": "el-real-call",
                "session_nonce": nonce,
            },
        )
        assert resp.status_code == 200

    resp = client.post(
        "/api/voice/session/started",
        json={
            "conversation_id": conversation_id,
            "elevenlabs_conversation_id": "el-real-call",
            "session_nonce": nonce,
        },
    )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# /api/voice/tools/faq, /api/voice/tools/push -- shared secret auth + logic.
# ---------------------------------------------------------------------------


def test_voice_tool_faq_returns_503_when_secret_not_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "")
    resp = client.post(
        "/api/voice/tools/faq",
        json={"conversation_id": "conv1", "question_number": 1},
    )
    assert resp.status_code == 503


def test_voice_tool_faq_rejects_wrong_bearer(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "correct-secret")
    resp = client.post(
        "/api/voice/tools/faq",
        json={"conversation_id": "conv1", "question_number": 1},
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


def test_voice_tool_faq_returns_same_answer_as_text_faq_tool(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "correct-secret")
    resp = client.post(
        "/api/voice/tools/faq",
        json={"conversation_id": "conv1", "question_number": 1},
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert resp.status_code == 200
    faq1 = knowledge.find_faq(1)
    assert resp.json()["result"] == knowledge.format_faq_answer(faq1)


def test_voice_tool_faq_unknown_number(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "correct-secret")
    resp = client.post(
        "/api/voice/tools/faq",
        json={"conversation_id": "conv1", "question_number": 9999},
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert resp.status_code == 200
    assert "not found" in resp.json()["result"].lower()


def test_voice_tool_push_calls_pushover_and_marks_used(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "correct-secret")

    calls = {}

    def _fake_pushover(msg):
        calls["message"] = msg
        return "sent"

    def _fake_mark_used(cid):
        calls["conversation_id"] = cid

    monkeypatch.setattr(agent_runner, "send_pushover_notification", _fake_pushover)
    monkeypatch.setattr(db, "mark_push_tool_used", _fake_mark_used)

    resp = client.post(
        "/api/voice/tools/push",
        json={"conversation_id": "conv1", "message": "visitor wants to connect"},
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "sent"
    assert calls["message"] == "visitor wants to connect"
    assert calls["conversation_id"] == "conv1"


# ---------------------------------------------------------------------------
# /api/voice/webhook -- signature verification + transcript logging, mocked db.
# ---------------------------------------------------------------------------


def test_voice_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    resp = client.post(
        "/api/voice/webhook",
        content=b'{"type": "post_call_transcription", "data": {}}',
        headers={"elevenlabs-signature": "t=1,v0=deadbeef"},
    )
    assert resp.status_code == 401


def test_voice_webhook_ignores_non_transcript_events(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    body = json.dumps({"type": "some_other_event", "data": {}}).encode()
    header = _sign("shh", int(time.time()), body)
    resp = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})
    assert resp.status_code == 200
    assert resp.json()["skipped"]


def test_voice_webhook_skips_when_claim_fails(client, monkeypatch):
    """Redelivery or unknown session: claim_transcript_write returns None -> no-op 200."""
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    monkeypatch.setattr(db, "claim_transcript_write", lambda eid: None)
    body = json.dumps(
        {"type": "post_call_transcription", "data": {"conversation_id": "elid-1", "transcript": []}}
    ).encode()
    header = _sign("shh", int(time.time()), body)
    resp = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})
    assert resp.status_code == 200
    assert resp.json()["skipped"]


def test_voice_webhook_writes_transcript_and_flags_needs_attention(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    our_conversation_id = str(uuid.uuid4())
    monkeypatch.setattr(
        db,
        "claim_transcript_write",
        lambda eid: {"conversation_id": our_conversation_id, "push_tool_used": True},
    )

    inserted = []

    def _fake_insert(conversation_id, role, content, **kwargs):
        row = {"id": len(inserted) + 1, "conversation_id": conversation_id, "role": role, "content": content}
        inserted.append(row)
        return row

    monkeypatch.setattr(db, "insert_message", _fake_insert)
    monkeypatch.setattr(db, "get_existing_voice_turns", lambda cid: {})
    flagged = {}
    monkeypatch.setattr(db, "set_needs_attention", lambda message_id: flagged.setdefault("id", message_id))

    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "elid-2",
                "transcript": [
                    {"role": "user", "message": "Hi there"},
                    {"role": "agent", "message": "Hello! How can I help?"},
                ],
            },
        }
    ).encode()
    header = _sign("shh", int(time.time()), body)
    resp = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})

    assert resp.status_code == 200
    assert resp.json()["messages_saved"] == 2
    assert [r["role"] for r in inserted] == ["visitor", "avatar"]
    assert inserted[0]["content"] == "Hi there"
    assert inserted[1]["content"] == "Hello! How can I help?"
    assert flagged["id"] == inserted[1]["id"]  # flagged on the last avatar turn


def test_voice_webhook_releases_claim_and_returns_500_on_partial_failure(client, monkeypatch):
    """RECS.md: 'Voice transcript write can silently lose data on a retried webhook' --
    claim_transcript_write used to flip permanently before any row was inserted, so a
    mid-loop failure meant a redelivery found transcript_saved already True and
    silently skipped the rest forever. Now a failure releases the claim."""
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    our_conversation_id = str(uuid.uuid4())
    monkeypatch.setattr(
        db,
        "claim_transcript_write",
        lambda eid: {"conversation_id": our_conversation_id, "push_tool_used": False},
    )
    monkeypatch.setattr(db, "get_existing_voice_turns", lambda cid: {})

    inserted = []

    def _fake_insert(conversation_id, role, content, **kwargs):
        if len(inserted) == 1:
            raise RuntimeError("simulated transient Supabase failure")
        row = {"id": len(inserted) + 1, "conversation_id": conversation_id, "role": role, "content": content}
        inserted.append(row)
        return row

    monkeypatch.setattr(db, "insert_message", _fake_insert)
    released = {}
    monkeypatch.setattr(db, "release_transcript_claim", lambda eid: released.setdefault("id", eid))

    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "elid-partial",
                "transcript": [
                    {"role": "user", "message": "First turn"},
                    {"role": "agent", "message": "Second turn"},
                    {"role": "user", "message": "Third turn"},
                ],
            },
        }
    ).encode()
    header = _sign("shh", int(time.time()), body)
    resp = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})

    assert resp.status_code == 500
    assert len(inserted) == 1  # only the first turn made it in before the failure
    assert released["id"] == "elid-partial"


def test_voice_webhook_retry_skips_already_saved_turns(client, monkeypatch):
    """A redelivery after a partial failure re-inserts only the turns that never
    made it in, using (role, content) already on file for the conversation."""
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    our_conversation_id = str(uuid.uuid4())
    monkeypatch.setattr(
        db,
        "claim_transcript_write",
        lambda eid: {"conversation_id": our_conversation_id, "push_tool_used": True},
    )
    # Simulates the first turn having already been saved by an earlier, failed attempt.
    monkeypatch.setattr(db, "get_existing_voice_turns", lambda cid: {("visitor", "First turn"): 101})

    inserted = []

    def _fake_insert(conversation_id, role, content, **kwargs):
        row = {"id": len(inserted) + 200, "conversation_id": conversation_id, "role": role, "content": content}
        inserted.append(row)
        return row

    monkeypatch.setattr(db, "insert_message", _fake_insert)
    flagged = {}
    monkeypatch.setattr(db, "set_needs_attention", lambda message_id: flagged.setdefault("id", message_id))

    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "elid-retry",
                "transcript": [
                    {"role": "user", "message": "First turn"},
                    {"role": "agent", "message": "Second turn"},
                ],
            },
        }
    ).encode()
    header = _sign("shh", int(time.time()), body)
    resp = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})

    assert resp.status_code == 200
    assert resp.json()["messages_saved"] == 1  # only the new turn was actually inserted
    assert len(inserted) == 1
    assert inserted[0]["content"] == "Second turn"
    assert flagged["id"] == inserted[0]["id"]  # needs_attention still applied on the new avatar turn


# ---------------------------------------------------------------------------
# voice_live: needs the real `channel` column + `voice_sessions` table.
# ---------------------------------------------------------------------------


@pytest.mark.voice_live
def test_session_started_records_mapping_and_is_looked_up(client):
    conversation_id = str(uuid.uuid4())
    elevenlabs_conversation_id = f"el-{uuid.uuid4()}"
    nonce = security.mint_voice_session_nonce(conversation_id)
    resp = client.post(
        "/api/voice/session/started",
        json={
            "conversation_id": conversation_id,
            "elevenlabs_conversation_id": elevenlabs_conversation_id,
            "session_nonce": nonce,
        },
    )
    assert resp.status_code == 200
    assert db.get_conversation_id_for_voice_session(elevenlabs_conversation_id) == conversation_id


@pytest.mark.voice_live
def test_claim_transcript_write_is_idempotent(client):
    conversation_id = str(uuid.uuid4())
    elevenlabs_conversation_id = f"el-{uuid.uuid4()}"
    db.record_voice_session(elevenlabs_conversation_id, conversation_id)

    first = db.claim_transcript_write(elevenlabs_conversation_id)
    assert first == {"conversation_id": conversation_id, "push_tool_used": False}

    second = db.claim_transcript_write(elevenlabs_conversation_id)
    assert second is None


@pytest.mark.voice_live
def test_full_voice_webhook_flow_persists_channel_voice_rows(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    conversation_id = str(uuid.uuid4())
    elevenlabs_conversation_id = f"el-{uuid.uuid4()}"
    nonce = security.mint_voice_session_nonce(conversation_id)
    started = client.post(
        "/api/voice/session/started",
        json={
            "conversation_id": conversation_id,
            "elevenlabs_conversation_id": elevenlabs_conversation_id,
            "session_nonce": nonce,
        },
    )
    assert started.status_code == 200

    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": elevenlabs_conversation_id,
                "transcript": [
                    {"role": "user", "message": "Can I get in touch?"},
                    {"role": "agent", "message": "Sure, what's your email?"},
                ],
            },
        }
    ).encode()
    header = _sign("shh", int(time.time()), body)
    resp = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})
    assert resp.status_code == 200

    persisted = db.get_conversation_messages(conversation_id)
    assert len(persisted) == 2
    assert persisted[0]["role"] == "visitor"
    assert persisted[0]["channel"] == "voice"
    assert persisted[1]["role"] == "avatar"
    assert persisted[1]["channel"] == "voice"


@pytest.mark.voice_live
def test_voice_webhook_retry_against_real_db_recovers_from_partial_failure(client, monkeypatch):
    """End-to-end against the real voice_sessions/messages tables: a mid-loop
    failure releases the claim (transcript_saved back to False), and a redelivery
    completes the transcript without duplicating the turn that already saved."""
    monkeypatch.setattr(config, "ELEVENLABS_WEBHOOK_SECRET", "shh")
    conversation_id = str(uuid.uuid4())
    elevenlabs_conversation_id = f"el-{uuid.uuid4()}"
    db.record_voice_session(elevenlabs_conversation_id, conversation_id)

    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": elevenlabs_conversation_id,
                "transcript": [
                    {"role": "user", "message": "First turn survives"},
                    {"role": "agent", "message": "Second turn fails first try"},
                ],
            },
        }
    ).encode()
    header = _sign("shh", int(time.time()), body)

    real_insert = db.insert_message
    calls = {"count": 0}

    def _fail_on_second_turn(conversation_id, role, content, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated transient failure")
        return real_insert(conversation_id, role, content, **kwargs)

    monkeypatch.setattr(db, "insert_message", _fail_on_second_turn)
    first_attempt = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header})
    assert first_attempt.status_code == 500

    after_failure = db.get_conversation_messages(conversation_id)
    assert len(after_failure) == 1
    assert after_failure[0]["content"] == "First turn survives"

    monkeypatch.setattr(db, "insert_message", real_insert)
    header2 = _sign("shh", int(time.time()), body)
    retry = client.post("/api/voice/webhook", content=body, headers={"elevenlabs-signature": header2})
    assert retry.status_code == 200
    assert retry.json()["messages_saved"] == 1  # only the turn that failed last time

    final = db.get_conversation_messages(conversation_id)
    assert len(final) == 2  # no duplicate of the first turn
    assert [m["content"] for m in final] == ["First turn survives", "Second turn fails first try"]
