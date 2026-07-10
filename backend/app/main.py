"""FastAPI app: visitor chat API (SSE), admin API, voice API, and static UI serving."""

import asyncio
import json
import logging
import uuid

import requests
from agents import Runner
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai.types.responses import ResponseTextDeltaEvent

from . import agent_runner, config, db, knowledge, ratelimit, security, transcript, voice
from .schemas import (
    AdminLoginRequest,
    AdminMessageRequest,
    ChatRequest,
    VoiceFaqToolRequest,
    VoicePushToolRequest,
    VoiceSessionRequest,
    VoiceSessionStartedRequest,
)

logger = logging.getLogger("avatar")

app = FastAPI(title="Avatar")


def _validate_conversation_id(conversation_id: str) -> None:
    try:
        uuid.UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid conversation_id") from exc


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@app.get("/api/config")
async def get_config():
    return {"owner_name": config.OWNER_NAME}


@app.get("/api/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    _validate_conversation_id(conversation_id)
    rows = db.get_conversation_messages(conversation_id)
    return {"conversation_id": conversation_id, "messages": rows}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    _validate_conversation_id(payload.conversation_id)
    conversation_id = payload.conversation_id

    if not ratelimit.allow_chat_message(conversation_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "You're sending messages too quickly. Please wait a moment and try again."
            },
        )

    message = payload.message
    if len(message) > config.MAX_MESSAGE_CHARS:
        message = message[: config.MAX_MESSAGE_CHARS] + config.TRUNCATION_NOTE

    visitor_name = (payload.name or "").strip() or None
    visitor_row = db.insert_message(
        conversation_id, "visitor", message, conversation_name=visitor_name
    )

    async def event_stream():
        yield _sse("visitor", {"message": visitor_row})

        instant_number = knowledge.match_instant_answer(message)
        if instant_number is not None:
            faq = knowledge.find_faq(instant_number)
            if faq:
                answer = f"**Q{instant_number}:** {faq['question']}\n\n{faq['answer']}"
            else:
                answer = f"Q{instant_number} isn't one of the FAQ numbers I have on file."
            yield _sse("token", {"text": answer})
            row = db.insert_message(
                conversation_id,
                "avatar",
                answer,
                tool_calls=["instant_faq"] if faq else None,
            )
            yield _sse("done", {"message": row, "instant": instant_number})
            return

        rows = db.get_conversation_messages(conversation_id)
        prompt = transcript.build_transcript(rows, config.OWNER_NAME)
        agent = agent_runner.get_agent()

        full_text = ""
        tools_used: list[str] = []
        try:
            result = Runner.run_streamed(agent, input=prompt)
            async for event in result.stream_events():
                if event.type == "raw_response_event" and isinstance(
                    event.data, ResponseTextDeltaEvent
                ):
                    full_text += event.data.delta
                    yield _sse("token", {"text": event.data.delta})
                elif event.type == "run_item_stream_event":
                    if event.name == "tool_called":
                        tool_name = getattr(event.item, "tool_name", None)
                        if tool_name:
                            tools_used.append(tool_name)
                            yield _sse("tool", {"name": tool_name, "status": "called"})
                    elif event.name == "tool_output":
                        tool_name = tools_used[-1] if tools_used else None
                        yield _sse("tool", {"name": tool_name, "status": "done"})
        except Exception:
            logger.exception("Agent run failed for conversation %s", conversation_id)
            if not full_text:
                full_text = "Sorry, something went wrong on my end. Please try again in a moment."
                yield _sse("token", {"text": full_text})

        row = db.insert_message(
            conversation_id,
            "avatar",
            full_text,
            tool_calls=tools_used or None,
            needs_attention="push_tool" in tools_used,
        )
        yield _sse("done", {"message": row})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Voice API (SPEC-VOICE.md) -- ElevenLabs owns the real-time STT/LLM/TTS loop;
# these routes only mint a connection credential, receive tool-call webhooks, and
# log the finished transcript. None of them sit in the per-token hot path.
# ---------------------------------------------------------------------------


@app.post("/api/voice/session")
async def voice_session(payload: VoiceSessionRequest):
    _validate_conversation_id(payload.conversation_id)
    if not ratelimit.allow_voice_session(payload.conversation_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "You're starting voice sessions too quickly. Please wait a moment and try again."
            },
        )
    try:
        token = voice.mint_conversation_token()
    except voice.VoiceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except requests.RequestException:
        logger.exception("Failed to mint an ElevenLabs conversation token")
        raise HTTPException(
            status_code=502, detail="Couldn't reach the voice service. Please try again in a moment."
        ) from None
    return {
        "token": token,
        "agent_id": config.ELEVENLABS_AGENT_ID,
        "max_session_seconds": config.VOICE_MAX_SESSION_SECONDS,
    }


@app.post("/api/voice/session/started")
async def voice_session_started(payload: VoiceSessionStartedRequest):
    _validate_conversation_id(payload.conversation_id)
    db.record_voice_session(payload.elevenlabs_conversation_id, payload.conversation_id)
    return {"ok": True}


@app.post("/api/voice/tools/faq", dependencies=[Depends(security.require_voice_tool_secret)])
async def voice_tool_faq(payload: VoiceFaqToolRequest):
    faq = knowledge.find_faq(payload.question_number)
    if not faq:
        return {"result": "That question number was not found in the FAQ."}
    return {"result": knowledge.format_faq_answer(faq)}


@app.post("/api/voice/tools/push", dependencies=[Depends(security.require_voice_tool_secret)])
async def voice_tool_push(payload: VoicePushToolRequest):
    result = await asyncio.to_thread(agent_runner.send_pushover_notification, payload.message)
    db.mark_push_tool_used(payload.conversation_id)
    return {"result": result}


@app.post("/api/voice/webhook")
async def voice_webhook(request: Request):
    raw_body = await request.body()
    signature_header = request.headers.get("elevenlabs-signature")
    if not voice.verify_webhook_signature(raw_body, signature_header):
        # Signature format hasn't been exercised against a real payload yet (see
        # SPEC-VOICE.md's open items) -- log what we actually received so a live
        # failure is diagnosable without another debug-script round trip.
        logger.warning(
            "Voice webhook signature check failed. header=%r all_headers=%r body_preview=%r",
            signature_header,
            dict(request.headers),
            raw_body[:500],
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    if payload.get("type") != "post_call_transcription":
        return {"ok": True, "skipped": "not a post_call_transcription event"}

    data = payload.get("data", {})
    elevenlabs_conversation_id = data.get("conversation_id")
    if not elevenlabs_conversation_id:
        raise HTTPException(status_code=400, detail="Missing conversation_id in webhook payload")

    claim = db.claim_transcript_write(elevenlabs_conversation_id)
    if claim is None:
        # Either an unknown session, or (far more likely) a redelivery of a transcript
        # we already saved -- either way, 200 so ElevenLabs doesn't keep retrying.
        return {"ok": True, "skipped": "already saved or unknown session"}

    conversation_id = claim["conversation_id"]
    transcript_turns = data.get("transcript", [])
    last_avatar_row = None
    for turn in transcript_turns:
        turn_role = turn.get("role")
        text = turn.get("message") or turn.get("text") or turn.get("content") or ""
        if not text:
            continue
        role = "visitor" if turn_role == "user" else "avatar"
        row = db.insert_message(conversation_id, role, text, channel="voice")
        if role == "avatar":
            last_avatar_row = row

    if claim["push_tool_used"] and last_avatar_row:
        db.set_needs_attention(last_avatar_row["id"])

    return {"ok": True, "messages_saved": len(transcript_turns)}


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


@app.post("/admin/login")
async def admin_login(payload: AdminLoginRequest, response: Response):
    if payload.password != config.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect password")
    response.set_cookie(
        key=config.ADMIN_SESSION_COOKIE,
        value=security.create_session_token(),
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        max_age=security.SESSION_MAX_AGE,
        path="/",
    )
    return {"ok": True}


@app.post("/admin/logout")
async def admin_logout(response: Response):
    response.delete_cookie(config.ADMIN_SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/admin/conversations", dependencies=[Depends(security.require_admin)])
async def admin_list_conversations():
    return {"conversations": db.list_inbox()}


@app.get(
    "/admin/conversations/{conversation_id}",
    dependencies=[Depends(security.require_admin)],
)
async def admin_open_conversation(conversation_id: str):
    _validate_conversation_id(conversation_id)
    rows = db.open_conversation(conversation_id)
    return {"conversation_id": conversation_id, "messages": rows}


@app.post(
    "/admin/conversations/{conversation_id}/messages",
    dependencies=[Depends(security.require_admin)],
)
async def admin_post_message(conversation_id: str, payload: AdminMessageRequest):
    _validate_conversation_id(conversation_id)
    row = db.insert_message(conversation_id, "human", payload.content, read=True)
    return {"message": row}


@app.post(
    "/admin/conversations/{conversation_id}/resolve",
    dependencies=[Depends(security.require_admin)],
)
async def admin_resolve_conversation(conversation_id: str):
    _validate_conversation_id(conversation_id)
    db.resolve_conversation(conversation_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Static UI (built frontend, if present)
# ---------------------------------------------------------------------------

if config.FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=config.FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(config.FRONTEND_DIST / "index.html")

    @app.get("/admin", include_in_schema=False)
    async def serve_admin():
        return FileResponse(config.FRONTEND_DIST / "admin.html")

    @app.get("/voice", include_in_schema=False)
    async def serve_voice():
        return FileResponse(config.FRONTEND_DIST / "voice.html")

    @app.get("/{filename}", include_in_schema=False)
    async def serve_public_file(filename: str):
        file_path = config.FRONTEND_DIST / filename
        if file_path.is_file():
            return FileResponse(file_path)
        raise HTTPException(status_code=404)
