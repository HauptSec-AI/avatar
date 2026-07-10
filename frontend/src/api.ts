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

export async function adminListConversations(): Promise<ConversationSummary[]> {
  const r = await adminFetch("/admin/conversations");
  const body = await r.json();
  return body.conversations;
}

export async function adminOpenConversation(id: string): Promise<Message[]> {
  const r = await adminFetch(`/admin/conversations/${id}`);
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
