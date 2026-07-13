"""Shared fixtures for backend tests.

Loads the real project-root .env (same as app.config), then provides:
- `client`: a plain FastAPI TestClient (no auth).
- `admin_client`: a TestClient already logged in as admin (cookie attached).
- `fake_stream_events`: helper to build a fake agents.Runner.run_streamed() result
  so chat tests can avoid a real LLM call.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from openai.types.responses import ResponseTextDeltaEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.main import app  # noqa: E402
from app import config  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def admin_client() -> TestClient:
    c = TestClient(app)
    resp = c.post("/admin/login", json={"password": config.ADMIN_PASSWORD})
    assert resp.status_code == 200
    return c


def _text_delta_event(delta: str):
    data = ResponseTextDeltaEvent(
        content_index=0,
        delta=delta,
        item_id="fake-item",
        logprobs=[],
        output_index=0,
        sequence_number=0,
        type="response.output_text.delta",
    )
    return SimpleNamespace(type="raw_response_event", data=data)


def _tool_called_event(tool_name: str, call_id: str | None = None):
    item = SimpleNamespace(tool_name=tool_name, call_id=call_id)
    return SimpleNamespace(type="run_item_stream_event", name="tool_called", item=item)


def _tool_output_event(call_id: str | None = None):
    item = SimpleNamespace(call_id=call_id) if call_id else None
    return SimpleNamespace(type="run_item_stream_event", name="tool_output", item=item)


class _FakeRunResultStreaming:
    """Mimics the subset of agents.result.RunResultStreaming that main.py touches."""

    def __init__(self, events: list[Any]):
        self._events = events

    async def stream_events(self):
        for event in self._events:
            yield event


def make_fake_run_streamed(text: str = "Hello from a fake agent.", tool_name: str | None = None):
    """Build a callable to monkeypatch onto agents.Runner.run_streamed.

    Returns a function with the same call signature (agent, input=...) that
    yields text deltas (and optionally a tool call) with no real LLM call.
    """
    events: list[Any] = []
    if tool_name:
        events.append(_tool_called_event(tool_name, call_id="call_1"))
        events.append(_tool_output_event(call_id="call_1"))
    events.append(_text_delta_event(text))

    def _fake_run_streamed(agent, input=None, **kwargs):
        return _FakeRunResultStreaming(events)

    return _fake_run_streamed


def make_fake_run_streamed_two_tools_out_of_order(text: str = "Done."):
    """Two tools called in order [faq_tool, push_tool], but push_tool's output
    arrives FIRST -- exercises call_id-based correlation of "tool_output" events
    instead of a naive last-called-therefore-next-done (stack) assumption, which
    mislabels whichever tool actually finishes out of call order.
    """
    events = [
        _tool_called_event("faq_tool", call_id="call_1"),
        _tool_called_event("push_tool", call_id="call_2"),
        _tool_output_event(call_id="call_2"),  # push_tool finishes first
        _tool_output_event(call_id="call_1"),  # faq_tool finishes second
        _text_delta_event(text),
    ]

    def _fake_run_streamed(agent, input=None, **kwargs):
        return _FakeRunResultStreaming(events)

    return _fake_run_streamed
