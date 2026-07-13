"""Tests for agent_runner.send_pushover_notification: the coarse GLOBAL rate
limit that protects against a script minting a fresh conversation_id per
request to flood Pushover past the per-conversation 20/minute chat limit
(RECS.md: "Rate limit is per free-mint conversation_id")."""

import pytest
import requests

from app import agent_runner, config, ratelimit


@pytest.fixture(autouse=True)
def _reset_push_tool_limiter():
    ratelimit._limiter.clear(ratelimit._push_tool_rate, "push_tool_global")
    yield
    ratelimit._limiter.clear(ratelimit._push_tool_rate, "push_tool_global")


def test_send_pushover_notification_not_configured(monkeypatch):
    monkeypatch.setattr(config, "PUSHOVER_USER", "")
    monkeypatch.setattr(config, "PUSHOVER_TOKEN", "")
    result = agent_runner.send_pushover_notification("hello")
    assert "not configured" in result.lower()


def test_send_pushover_notification_calls_pushover_when_configured(monkeypatch):
    monkeypatch.setattr(config, "PUSHOVER_USER", "u")
    monkeypatch.setattr(config, "PUSHOVER_TOKEN", "t")

    class _FakeResponse:
        status_code = 200

    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse())
    result = agent_runner.send_pushover_notification("hello")
    assert "200" in result


def test_send_pushover_notification_rate_limited_globally_across_conversations(monkeypatch):
    """A script minting a fresh conversation_id per call never touches the
    per-conversation chat limiter at all -- this bucket has no conversation_id
    identifier, so it caps total sends regardless of how many IDs are used."""
    monkeypatch.setattr(config, "PUSHOVER_USER", "u")
    monkeypatch.setattr(config, "PUSHOVER_TOKEN", "t")

    class _FakeResponse:
        status_code = 200

    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse())

    limit = int(config.PUSH_TOOL_RATE_LIMIT.split("/")[0])
    for _ in range(limit):
        result = agent_runner.send_pushover_notification("hello")
        assert "200" in result

    blocked = agent_runner.send_pushover_notification("hello")
    assert "already been notified" in blocked.lower()
