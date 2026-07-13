"""ElevenLabs Agents platform integration (SPEC-VOICE.md).

Three jobs, none of which sit in the per-token hot path -- ElevenLabs' own
infrastructure owns the real-time STT -> LLM -> TTS loop once a session starts:

1. Mint a short-lived connection credential for the browser (`mint_conversation_token`).
2. Verify the signed post-call transcript webhook (`verify_webhook_signature`).
3. Build the agent-config payload used to (re)provision the agent (`build_agent_config`),
   shared between the one-off `scripts/sync_voice_agent.py` and this module.

Endpoint paths and the agent-config payload shape are ElevenLabs' current documented
surface as of writing this; both are isolated in this module specifically so they're
one place to fix if the live API disagrees once real credentials are available (see
SPEC-VOICE.md's "Open technical items to verify at implementation time").
"""

import hashlib
import hmac
import time

import requests

from . import config, knowledge

API_BASE = "https://api.elevenlabs.io/v1"
WEBHOOK_SIGNATURE_TOLERANCE_SECONDS = 30 * 60  # 30 min, matches ElevenLabs' documented tolerance


class VoiceNotConfigured(RuntimeError):
    """Raised when a voice route is hit before ELEVENLABS_* env vars are set."""


def _require_configured() -> None:
    if not (config.ELEVENLABS_API_KEY and config.ELEVENLABS_AGENT_ID):
        raise VoiceNotConfigured(
            "Voice isn't configured yet -- set ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID "
            "(see SPEC-VOICE.md Setup and Validation)."
        )


def mint_conversation_token() -> str:
    """Mint a short-lived WebRTC conversation token scoped to our agent.

    The browser uses this (never the raw API key) to open its ElevenLabs session.
    Verify this endpoint against ElevenLabs' current docs before relying on it live --
    it's the one piece of this module most likely to need a path/response-shape tweak.
    """
    _require_configured()
    response = requests.get(
        f"{API_BASE}/convai/conversation/token",
        params={"agent_id": config.ELEVENLABS_AGENT_ID},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["token"]


def verify_webhook_signature(payload: bytes, signature_header: str | None) -> bool:
    """Verify the `ElevenLabs-Signature` header on the post-call webhook.

    Format is `t=<unix_ts>,v0=<hex_hmac_sha256>` (Stripe-style): the HMAC is computed
    over `f"{ts}.{payload}"` with ELEVENLABS_WEBHOOK_SECRET, and the timestamp must be
    recent to reject replays.
    """
    if not signature_header or not config.ELEVENLABS_WEBHOOK_SECRET:
        return False

    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    ts = parts.get("t")
    signature = parts.get("v0")
    if not ts or not signature:
        return False

    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > WEBHOOK_SIGNATURE_TOLERANCE_SECONDS:
        return False

    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        config.ELEVENLABS_WEBHOOK_SECRET.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _tool_webhook_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _tool_auth_headers() -> dict:
    # Static bearer header ElevenLabs sends on every tool call; our backend checks it
    # in security.require_voice_tool_secret (both sides read ELEVENLABS_TOOL_SECRET --
    # a dedicated secret, separate from ELEVENLABS_WEBHOOK_SECRET's HMAC-signing use).
    return {"Authorization": f"Bearer {config.ELEVENLABS_TOOL_SECRET}"}


VOICE_PROMPT_ADDENDUM = """

# Voice mode

You are in a live VOICE conversation right now, not text chat -- everything you say is read
aloud by text-to-speech. Never use Markdown (no **bold**, no [links](url), no bullet lists,
no headers): speak in plain, natural sentences. Keep responses noticeably shorter than you
would in text -- a sentence or two per turn, not a paragraph -- and pause for the visitor to
react rather than delivering a monologue. If you'd normally share a link (e.g. from the FAQ),
say what it is in words instead ("you can find that on my LinkedIn") rather than reading a URL
aloud."""


def build_agent_config(base_url: str) -> dict:
    """The agent-config payload used to create/update the ElevenLabs agent.

    `base_url` is this deployment's own public URL (e.g. https://avatar-alex.fly.dev),
    used to build the two tool webhook URLs. Shared by scripts/sync_voice_agent.py.

    Uses ElevenLabs' managed LLM (`config.ELEVENLABS_LLM`), not Custom LLM/OpenRouter:
    ElevenLabs rejects Custom LLM on agents using an Instant Voice Clone ("Custom LLM is
    not allowed when using agents with Instant Voice Clones"), discovered via a live 400
    against a real account. Text chat is unaffected -- still OpenRouter/MODEL.
    """
    first_name = config.OWNER_NAME.split(" ")[0]
    return {
        "name": f"{config.OWNER_NAME}'s Digital Twin (Voice)",
        "conversation_config": {
            "agent": {
                "first_message": f"Hey, this is {first_name}'s digital twin -- go ahead, what's on your mind?",
                "prompt": {
                    "prompt": knowledge.build_instructions() + VOICE_PROMPT_ADDENDUM,
                    "llm": config.ELEVENLABS_LLM,
                    "tools": [
                        {
                            "type": "webhook",
                            "name": "faq_tool",
                            "description": (
                                "Retrieve the full, original answer to a frequently "
                                "asked question by its number."
                            ),
                            "api_schema": {
                                "url": _tool_webhook_url(base_url, "/api/voice/tools/faq"),
                                "method": "POST",
                                "request_headers": _tool_auth_headers(),
                                "request_body_schema": {
                                    "type": "object",
                                    "properties": {
                                        "conversation_id": {
                                            "type": "string",
                                            "dynamic_variable": "conversation_id",
                                        },
                                        "question_number": {
                                            "type": "integer",
                                            "description": "The FAQ number to look up.",
                                        },
                                    },
                                    "required": ["conversation_id", "question_number"],
                                },
                            },
                        },
                        {
                            "type": "webhook",
                            "name": "push_tool",
                            "description": (
                                f"Send the given message to {config.OWNER_NAME} "
                                "(your human twin) as a Pushover notification."
                            ),
                            "api_schema": {
                                "url": _tool_webhook_url(base_url, "/api/voice/tools/push"),
                                "method": "POST",
                                "request_headers": _tool_auth_headers(),
                                "request_body_schema": {
                                    "type": "object",
                                    "properties": {
                                        "conversation_id": {
                                            "type": "string",
                                            "dynamic_variable": "conversation_id",
                                        },
                                        "message": {
                                            "type": "string",
                                            "description": f"The message to send to {config.OWNER_NAME}.",
                                        },
                                    },
                                    "required": ["conversation_id", "message"],
                                },
                            },
                        },
                    ],
                },
            },
            "tts": {"voice_id": config.ELEVENLABS_VOICE_ID},
        },
    }


def sync_agent(base_url: str) -> dict:
    """Create (if ELEVENLABS_AGENT_ID is unset) or update the ElevenLabs agent."""
    if not config.ELEVENLABS_API_KEY:
        raise VoiceNotConfigured("ELEVENLABS_API_KEY is required to sync the voice agent.")

    payload = build_agent_config(base_url)
    headers = {"xi-api-key": config.ELEVENLABS_API_KEY}

    if config.ELEVENLABS_AGENT_ID:
        response = requests.patch(
            f"{API_BASE}/convai/agents/{config.ELEVENLABS_AGENT_ID}",
            json=payload,
            headers=headers,
            timeout=30,
        )
    else:
        response = requests.post(
            f"{API_BASE}/convai/agents/create", json=payload, headers=headers, timeout=30
        )
    response.raise_for_status()
    return response.json()
