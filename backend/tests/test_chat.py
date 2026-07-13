"""Tests for POST /api/chat: Qn instant answers, truncation, rate limiting,
and (a couple of) real end-to-end LLM calls.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app import config, db, knowledge
from app.main import app

from conftest import make_fake_run_streamed


def _parse_sse(raw_lines: list[str]) -> list[tuple[str, dict]]:
    """Parse `event: X\\ndata: Y` blocks from httpx's iter_lines() output into (event, data)."""
    events = []
    current_event = None
    for line in raw_lines:
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data = json.loads(line[len("data:") :].strip())
            events.append((current_event, data))
            current_event = None
    return events


def test_qn_shortcut_returns_faq_instantly_no_llm(client, monkeypatch):
    """A bare 'Q2' message should be answered from the FAQ file with no LLM call."""

    def _boom(*args, **kwargs):
        raise AssertionError("LLM should not be called for a Qn shortcut")

    monkeypatch.setattr("agents.Runner.run_streamed", _boom)

    conversation_id = str(uuid.uuid4())
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "name": "AB", "message": "Q2"},
    ) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    events = _parse_sse(lines)
    assert len(events) == 3
    visitor_event, token_event, done_event = events
    assert visitor_event[0] == "visitor"
    assert visitor_event[1]["message"]["content"] == "Q2"
    assert token_event[0] == "token"
    faq2 = knowledge.find_faq(2)
    assert faq2["question"] in token_event[1]["text"]
    assert faq2["answer"] in token_event[1]["text"]
    assert done_event[0] == "done"
    assert done_event[1]["instant"] == 2

    persisted = db.get_conversation_messages(conversation_id)
    assert len(persisted) == 2
    assert persisted[0]["role"] == "visitor"
    assert persisted[0]["content"] == "Q2"
    assert persisted[1]["role"] == "avatar"
    assert faq2["answer"] in persisted[1]["content"]
    assert persisted[1]["tool_calls"] == ["instant_faq"]


def test_qn_shortcut_case_insensitive(client, monkeypatch):
    monkeypatch.setattr(
        "agents.Runner.run_streamed",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM for Qn")),
    )
    conversation_id = str(uuid.uuid4())
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "message": "q1"},
    ) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    events = _parse_sse(lines)
    assert events[-1][1]["instant"] == 1
    persisted = db.get_conversation_messages(conversation_id)
    assert persisted[0]["content"] == "q1"


def test_qn_unknown_number_falls_back_to_message(client, monkeypatch):
    monkeypatch.setattr(
        "agents.Runner.run_streamed",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM for Qn")),
    )
    conversation_id = str(uuid.uuid4())
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "message": "Q99"},
    ) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    events = _parse_sse(lines)
    token_event = next(e for e in events if e[0] == "token")
    assert "isn't one of the FAQ numbers" in token_event[1]["text"]
    persisted = db.get_conversation_messages(conversation_id)
    assert persisted[1]["tool_calls"] is None


def test_long_message_is_truncated_and_noted(client, monkeypatch):
    """A >20,000 char message is clamped to 20,000 chars + truncation note, and
    that's what's stored (and what would be sent onward). Avoid a real LLM call
    by patching Runner.run_streamed with a fake streamed result.
    """
    monkeypatch.setattr(
        "agents.Runner.run_streamed", make_fake_run_streamed(text="Got it, thanks!")
    )

    conversation_id = str(uuid.uuid4())
    long_message = "a" * 25_000
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "message": long_message},
    ) as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())  # drain the stream

    persisted = db.get_conversation_messages(conversation_id)
    visitor_row = persisted[0]
    assert visitor_row["role"] == "visitor"
    expected_content = ("a" * config.MAX_MESSAGE_CHARS) + config.TRUNCATION_NOTE
    assert visitor_row["content"] == expected_content
    assert len(visitor_row["content"]) == config.MAX_MESSAGE_CHARS + len(config.TRUNCATION_NOTE)
    assert visitor_row["content"].endswith(
        "[...message truncated as it's too long; ask the visitor to send something more concise]"
    )


def test_message_at_limit_is_not_truncated(client, monkeypatch):
    monkeypatch.setattr("agents.Runner.run_streamed", make_fake_run_streamed(text="ok"))
    conversation_id = str(uuid.uuid4())
    exact_message = "b" * config.MAX_MESSAGE_CHARS
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "message": exact_message},
    ) as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())

    persisted = db.get_conversation_messages(conversation_id)
    assert persisted[0]["content"] == exact_message


def test_mocked_llm_reply_streams_tokens_and_persists_avatar_row(client, monkeypatch):
    monkeypatch.setattr(
        "agents.Runner.run_streamed",
        make_fake_run_streamed(text="Hello there, visitor!", tool_name="faq_tool"),
    )
    conversation_id = str(uuid.uuid4())
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "name": "CD", "message": "What courses do you offer?"},
    ) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    events = _parse_sse(lines)
    event_names = [e[0] for e in events]
    assert "tool" in event_names
    assert "token" in event_names
    assert event_names[-1] == "done"

    full_text = "".join(d["text"] for name, d in events if name == "token")
    assert full_text == "Hello there, visitor!"

    persisted = db.get_conversation_messages(conversation_id)
    assert len(persisted) == 2
    assert persisted[1]["role"] == "avatar"
    assert persisted[1]["content"] == "Hello there, visitor!"
    assert persisted[1]["tool_calls"] == ["faq_tool"]


def test_mocked_llm_push_tool_sets_needs_attention(client, monkeypatch):
    monkeypatch.setattr(
        "agents.Runner.run_streamed",
        make_fake_run_streamed(text="I've flagged this for the human.", tool_name="push_tool"),
    )
    conversation_id = str(uuid.uuid4())
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conversation_id, "message": "Can you connect me with a human?"},
    ) as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())

    persisted = db.get_conversation_messages(conversation_id)
    avatar_row = persisted[1]
    assert avatar_row["needs_attention"] is True
    assert avatar_row["tool_calls"] == ["push_tool"]


def test_message_over_max_body_length_returns_422(client):
    """ChatRequest.message has a hard max_length well above the 20k truncation
    clamp -- an oversized body is rejected outright rather than fully buffered
    (RECS.md: "No request body size limit")."""
    conversation_id = str(uuid.uuid4())
    too_long = "a" * (config.MAX_MESSAGE_BODY_CHARS + 1)
    resp = client.post(
        "/api/chat", json={"conversation_id": conversation_id, "message": too_long}
    )
    assert resp.status_code == 422


def test_oversized_request_body_returns_413(client):
    """Global body-size middleware rejects by Content-Length before any route
    (including ones with no per-field max_length) buffers the whole thing."""
    huge_body = b'{"conversation_id": "x", "message": "' + b"a" * config.MAX_REQUEST_BODY_BYTES + b'"}'
    resp = client.post(
        "/api/chat", content=huge_body, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 413


def test_invalid_conversation_id_returns_400(client):
    resp = client.post(
        "/api/chat", json={"conversation_id": "not-a-uuid", "message": "hello"}
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Rate limiting — 21st call within a minute for the same conversation_id
# returns 429 BEFORE any LLM call. Use Qn shortcuts (no LLM involved anyway)
# and also assert Runner.run_streamed is never invoked, proving the 429 gate
# happens first.
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_after_20_messages(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("LLM should not be called once rate-limited")

    monkeypatch.setattr("agents.Runner.run_streamed", _boom)

    conversation_id = str(uuid.uuid4())
    for i in range(20):
        with client.stream(
            "POST",
            "/api/chat",
            json={"conversation_id": conversation_id, "message": "Q1"},
        ) as resp:
            assert resp.status_code == 200
            list(resp.iter_lines())

    # 21st call in the same minute for the same conversation_id should be blocked.
    resp = client.post(
        "/api/chat", json={"conversation_id": conversation_id, "message": "Q1"}
    )
    assert resp.status_code == 429
    body = resp.json()
    assert "error" in body
    assert "quickly" in body["error"].lower()


def test_rate_limit_is_scoped_per_conversation_id(client, monkeypatch):
    """A fresh conversation_id is not affected by another conversation's rate limit."""
    monkeypatch.setattr(
        "agents.Runner.run_streamed",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM for Qn")),
    )
    exhausted_id = str(uuid.uuid4())
    for i in range(20):
        with client.stream(
            "POST",
            "/api/chat",
            json={"conversation_id": exhausted_id, "message": "Q1"},
        ) as resp:
            list(resp.iter_lines())
    blocked = client.post(
        "/api/chat", json={"conversation_id": exhausted_id, "message": "Q1"}
    )
    assert blocked.status_code == 429

    fresh_id = str(uuid.uuid4())
    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": fresh_id, "message": "Q1"},
    ) as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())


# ---------------------------------------------------------------------------
# Real end-to-end LLM calls (cheap: openai/gpt-5.4-nano). Kept to a minimum.
# ---------------------------------------------------------------------------


@pytest.mark.llm
def test_real_llm_reply_end_to_end():
    real_client = TestClient(app)
    conversation_id = str(uuid.uuid4())
    with real_client.stream(
        "POST",
        "/api/chat",
        json={
            "conversation_id": conversation_id,
            "name": "EF",
            "message": "In one short sentence, what's your current role?",
        },
    ) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    events = _parse_sse(lines)
    token_texts = [d["text"] for name, d in events if name == "token"]
    full_text = "".join(token_texts)
    assert full_text.strip() != ""
    assert events[-1][0] == "done"

    persisted = db.get_conversation_messages(conversation_id)
    assert len(persisted) == 2
    assert persisted[0]["role"] == "visitor"
    assert persisted[1]["role"] == "avatar"
    assert persisted[1]["content"].strip() != ""


@pytest.mark.llm
def test_real_llm_unknown_question_uses_push_tool_or_faq():
    """A question well outside the knowledge base should either get pushed to the
    human (needs_attention=True) or be answered via the FAQ tool -- either way the
    agent should respond with real, non-empty content rather than erroring out.
    """
    real_client = TestClient(app)
    conversation_id = str(uuid.uuid4())
    with real_client.stream(
        "POST",
        "/api/chat",
        json={
            "conversation_id": conversation_id,
            "message": "What is the capital of a fictional planet named Zorblax-9, and can you personally call me on the phone right now?",
        },
    ) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    events = _parse_sse(lines)
    full_text = "".join(d["text"] for name, d in events if name == "token")
    assert full_text.strip() != ""

    persisted = db.get_conversation_messages(conversation_id)
    avatar_row = persisted[1]
    assert avatar_row["content"].strip() != ""
