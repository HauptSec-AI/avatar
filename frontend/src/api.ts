import type { ConfigResponse, ConversationSummary, Message } from "./types";

export class AuthError extends Error {}

export async function getConfig(): Promise<ConfigResponse> {
  const r = await fetch("/api/config");
  return r.json();
}

export async function getConversation(conversationId: string): Promise<Message[]> {
  const r = await fetch(`/api/conversation/${conversationId}`);
  const body = await r.json();
  return body.messages;
}

export interface ChatStreamHandlers {
  onVisitorSaved: (message: Message) => void;
  onToken: (text: string) => void;
  onTool: (name: string | null, status: "called" | "done") => void;
  onDone: (message: Message) => void;
  onError: (message: string) => void;
}

export async function postChat(
  conversationId: string,
  name: string | null,
  message: string,
  handlers: ChatStreamHandlers,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, name, message }),
    });
  } catch {
    handlers.onError("Couldn't reach the server. Check your connection and try again.");
    return;
  }

  if (response.status === 429) {
    const body = await response
      .json()
      .catch(() => ({ error: "You're sending messages too quickly. Please wait a moment and try again." }));
    handlers.onError(body.error);
    return;
  }
  if (!response.ok || !response.body) {
    handlers.onError("Something went wrong reaching the server. Please try again.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");

        const lines = raw.split("\n");
        const eventLine = lines.find((l) => l.startsWith("event: "));
        const dataLine = lines.find((l) => l.startsWith("data: "));
        if (!eventLine || !dataLine) continue;

        const eventType = eventLine.slice("event: ".length);
        const data = JSON.parse(dataLine.slice("data: ".length));
        if (eventType === "visitor") handlers.onVisitorSaved(data.message);
        else if (eventType === "token") handlers.onToken(data.text);
        else if (eventType === "tool") handlers.onTool(data.name, data.status);
        else if (eventType === "done") handlers.onDone(data.message);
      }
    }
  } catch {
    // A dropped connection mid-stream throws out of reader.read() -- without this,
    // the exception would propagate out of postChat and skip sendMessage's
    // composer-reset code entirely, leaving the send button disabled until reload.
    handlers.onError("Lost connection to the server. Please try again.");
  }
}

// ---- Admin ----

export async function adminLogin(password: string): Promise<boolean> {
  const r = await fetch("/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return r.ok;
}

export async function adminLogout(): Promise<void> {
  await fetch("/admin/logout", { method: "POST" });
}

async function adminFetch(input: string, init?: RequestInit): Promise<Response> {
  const r = await fetch(input, init);
  if (r.status === 401) throw new AuthError();
  return r;
}

export interface AdminInboxResult {
  conversations: ConversationSummary[];
  scanTruncated: boolean;
}

export async function adminListConversations(): Promise<AdminInboxResult> {
  const r = await adminFetch("/admin/conversations");
  const body = await r.json();
  return { conversations: body.conversations, scanTruncated: Boolean(body.scan_truncated) };
}

export async function adminOpenConversation(id: string): Promise<Message[]> {
  // POST, not GET: opening a thread marks it read + clears needs_attention as a
  // side effect (one round trip, per SPEC-AVATAR.md) -- a state-mutating GET is
  // forgeable cross-site under SameSite=Lax via a top-level navigation, letting a
  // malicious link silently dismiss a flagged conversation.
  const r = await adminFetch(`/admin/conversations/${id}`, { method: "POST" });
  const body = await r.json();
  return body.messages;
}

export async function adminPostMessage(id: string, content: string): Promise<Message> {
  const r = await adminFetch(`/admin/conversations/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  const body = await r.json();
  return body.message;
}

export async function adminResolveConversation(id: string): Promise<void> {
  await adminFetch(`/admin/conversations/${id}/resolve`, { method: "POST" });
}

// ---- Voice (SPEC-VOICE.md) ----

export class VoiceSessionError extends Error {}

export interface VoiceSession {
  token: string;
  agentId: string;
  maxSessionSeconds: number;
  sessionNonce: string;
}

export async function startVoiceSession(conversationId: string): Promise<VoiceSession> {
  let response: Response;
  try {
    response = await fetch("/api/voice/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
  } catch {
    throw new VoiceSessionError("Couldn't reach the server. Check your connection and try again.");
  }

  if (response.status === 429) {
    const body = await response
      .json()
      .catch(() => ({ error: "You're starting voice sessions too quickly. Please wait a moment and try again." }));
    throw new VoiceSessionError(body.error);
  }
  if (response.status === 503) {
    throw new VoiceSessionError("Voice isn't available right now.");
  }
  if (!response.ok) {
    throw new VoiceSessionError("Couldn't start a voice session. Please try again.");
  }

  const body = await response.json();
  return {
    token: body.token,
    agentId: body.agent_id,
    maxSessionSeconds: body.max_session_seconds,
    sessionNonce: body.session_nonce,
  };
}

export async function notifyVoiceSessionStarted(
  conversationId: string,
  elevenlabsConversationId: string,
  sessionNonce: string,
): Promise<void> {
  try {
    await fetch("/api/voice/session/started", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        elevenlabs_conversation_id: elevenlabsConversationId,
        session_nonce: sessionNonce,
      }),
    });
  } catch {
    // Best-effort: if this fails, the post-call transcript just won't have a home to
    // land in. The live call itself is unaffected either way.
  }
}
