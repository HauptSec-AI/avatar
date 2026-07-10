import "./styles/chat.css";
import { getConfig, getConversation, postChat } from "./api";
import { deleteCookie, getCookie, setCookie } from "./cookies";
import { renderMarkdown } from "./markdown";
import { initials, instantTagHtml, renderMessageHTML } from "./render";
import { setupThemeToggle } from "./theme";
import type { Message } from "./types";

const COOKIE_NAME = "avatar_conversation_id";
const NAME_STORAGE_KEY = "avatar-name";
const POLL_FAST_MS = 10_000;
const POLL_SLOW_MS = 60_000;
const POLL_SLOWDOWN_AFTER_MS = 5 * 60_000;

const convoEl = document.getElementById("convo") as HTMLDivElement;
const convoInner = document.getElementById("convoInner") as HTMLDivElement;
const introEl = document.getElementById("intro") as HTMLDivElement;
const messageInput = document.getElementById("messageInput") as HTMLTextAreaElement;
const sendBtn = document.getElementById("sendBtn") as HTMLButtonElement;
const nameInput = document.getElementById("nameInput") as HTMLInputElement;
const keepChatToggle = document.getElementById("keepChatToggle") as HTMLInputElement;
const resetBtn = document.getElementById("resetBtn") as HTMLButtonElement;
const brandSub = document.getElementById("brandSub") as HTMLDivElement;
const introHeading = document.getElementById("introHeading") as HTMLHeadingElement;
const introBody = document.getElementById("introBody") as HTMLParagraphElement;
const suggestRow = document.getElementById("suggestRow") as HTMLDivElement;

let ownerName = "Avatar";
let conversationId = "";
let lastActivityAt = Date.now();
let pollTimer: number | undefined;
let sending = false;
const renderedIds = new Set<number>();

setupThemeToggle("themeToggle");

function scrollToLatest(): void {
  convoEl.scrollTop = convoEl.scrollHeight;
}

function humanTagHtml(): string {
  return `<span class="human-tag"><svg class="icon"><use href="/icons.svg#i-live"/></svg> ${ownerName} · live</span>`;
}

function appendMessage(row: Message): void {
  if (renderedIds.has(row.id)) return;
  renderedIds.add(row.id);
  introEl.style.display = "none";
  const wrapper = document.createElement("div");
  wrapper.innerHTML = renderMessageHTML(row, {
    humanTagHtml: humanTagHtml(),
    visitorInitials: initials(nameInput.value),
  });
  convoInner.appendChild(wrapper.firstElementChild!);
  scrollToLatest();
}

function renderHistory(rows: Message[]): void {
  for (const row of rows) appendMessage(row);
}

function showBanner(message: string): void {
  const el = document.createElement("div");
  el.className = "banner";
  el.textContent = message;
  convoInner.appendChild(el);
  scrollToLatest();
  window.setTimeout(() => el.remove(), 6000);
}

// ---- typing indicator ----
let typingEl: HTMLDivElement | null = null;
function showTyping(): void {
  if (typingEl) return;
  typingEl = document.createElement("div");
  typingEl.className = "typing";
  typingEl.innerHTML = `<span class="dots"><span></span><span></span><span></span></span> Avatar is typing`;
  convoInner.appendChild(typingEl);
  scrollToLatest();
}
function hideTyping(): void {
  typingEl?.remove();
  typingEl = null;
}

// ---- streaming avatar bubble ----
interface StreamingBubble {
  wrapper: HTMLDivElement;
  bubble: HTMLDivElement;
  metaEl: HTMLDivElement;
  text: string;
  toolStatusEls: Map<string, HTMLDivElement>;
}

function startAvatarBubble(): StreamingBubble {
  const wrapper = document.createElement("div");
  wrapper.className = "msg msg--avatar";
  wrapper.innerHTML = `
    <div class="avatar avatar-twin" style="background-image:url('/assets/avatar-robot-round.png')"></div>
    <div class="msg-body">
      <div class="msg-meta"><span class="msg-name">Avatar</span></div>
      <div class="bubble"></div>
    </div>`;
  convoInner.appendChild(wrapper);
  scrollToLatest();
  return {
    wrapper,
    bubble: wrapper.querySelector(".bubble") as HTMLDivElement,
    metaEl: wrapper.querySelector(".msg-meta") as HTMLDivElement,
    text: "",
    toolStatusEls: new Map(),
  };
}

const TOOL_LABELS: Record<string, { calling: string; done: string }> = {
  faq_tool: { calling: "Looking up the FAQ…", done: "Looked up the FAQ" },
  push_tool: { calling: "Notifying the human…", done: "Notified the human" },
};

function toolStatusHtml(name: string, done: boolean): string {
  const label = TOOL_LABELS[name] ?? { calling: `Calling ${name}…`, done: name };
  const icon = done ? "i-check" : "i-tool";
  return `<svg class="icon"><use href="/icons.svg#${icon}"/></svg> ${done ? label.done : label.calling}`;
}

// ---- composer ----
function autoResize(): void {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
}

function setComposerEnabled(enabled: boolean): void {
  messageInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

async function sendMessage(text: string): Promise<void> {
  const trimmed = text.trim();
  if (!trimmed || sending) return;

  sending = true;
  setComposerEnabled(false);
  messageInput.value = "";
  autoResize();
  lastActivityAt = Date.now();
  ensurePolling();
  showTyping();

  let bubbleState: StreamingBubble | null = null;

  await postChat(conversationId, nameInput.value.trim() || null, trimmed, {
    onVisitorSaved: (message) => {
      hideTyping();
      appendMessage(message);
      showTyping();
    },
    onToken: (delta) => {
      hideTyping();
      if (!bubbleState) bubbleState = startAvatarBubble();
      bubbleState.text += delta;
      bubbleState.bubble.innerHTML = renderMarkdown(bubbleState.text);
      scrollToLatest();
    },
    onTool: (name, status) => {
      hideTyping();
      if (!bubbleState) bubbleState = startAvatarBubble();
      if (!name) return;
      let el = bubbleState.toolStatusEls.get(name);
      if (!el) {
        el = document.createElement("div");
        el.className = "tool-status";
        bubbleState.metaEl.insertAdjacentElement("afterend", el);
        bubbleState.toolStatusEls.set(name, el);
      }
      el.classList.toggle("is-done", status === "done");
      el.innerHTML = toolStatusHtml(name, status === "done");
      scrollToLatest();
    },
    onDone: (message) => {
      hideTyping();
      renderedIds.add(message.id);
      if (bubbleState) {
        bubbleState.wrapper.dataset.id = String(message.id);
        const tag = instantTagHtml(message);
        if (tag) bubbleState.metaEl.insertAdjacentHTML("beforeend", tag);
      } else {
        appendMessage(message);
      }
    },
    onError: (msg) => {
      hideTyping();
      showBanner(msg);
    },
  });

  sending = false;
  setComposerEnabled(true);
  messageInput.focus();
}

messageInput.addEventListener("input", autoResize);
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    void sendMessage(messageInput.value);
  }
});
sendBtn.addEventListener("click", () => void sendMessage(messageInput.value));

nameInput.addEventListener("input", () => localStorage.setItem(NAME_STORAGE_KEY, nameInput.value));

// ---- conversation identity ----
function newConversationId(): string {
  return crypto.randomUUID();
}

keepChatToggle.addEventListener("change", () => {
  if (keepChatToggle.checked) setCookie(COOKIE_NAME, conversationId);
  else deleteCookie(COOKIE_NAME);
});

resetBtn.addEventListener("click", () => {
  conversationId = newConversationId();
  renderedIds.clear();
  convoInner.innerHTML = "";
  convoInner.appendChild(introEl);
  introEl.style.display = "";
  if (keepChatToggle.checked) setCookie(COOKIE_NAME, conversationId);
  else deleteCookie(COOKIE_NAME);
  lastActivityAt = Date.now();
  messageInput.focus();
});

async function initConversation(): Promise<void> {
  const existing = keepChatToggle.checked ? getCookie(COOKIE_NAME) : null;
  if (existing) {
    conversationId = existing;
    const rows = await getConversation(conversationId);
    renderHistory(rows);
  } else {
    conversationId = newConversationId();
    if (keepChatToggle.checked) setCookie(COOKIE_NAME, conversationId);
  }
}

// ---- polling for human messages ----
function ensurePolling(): void {
  if (pollTimer !== undefined) return;
  scheduleNextPoll();
}

function scheduleNextPoll(): void {
  const idleMs = Date.now() - lastActivityAt;
  const interval = idleMs > POLL_SLOWDOWN_AFTER_MS ? POLL_SLOW_MS : POLL_FAST_MS;
  pollTimer = window.setTimeout(() => {
    void pollForUpdates().finally(scheduleNextPoll);
  }, interval);
}

async function pollForUpdates(): Promise<void> {
  if (!conversationId || document.hidden) return;
  try {
    const rows = await getConversation(conversationId);
    renderHistory(rows);
  } catch {
    // transient network error; retry on the next tick
  }
}

// ---- Qn deep link (?q=N) ----
function consumeDeepLinkQuestion(): string | null {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  if (!q) return null;
  params.delete("q");
  const query = params.toString();
  const newUrl = window.location.pathname + (query ? `?${query}` : "") + window.location.hash;
  window.history.replaceState({}, "", newUrl);
  return `Q${q}`;
}

// ---- init ----
async function init(): Promise<void> {
  const cfg = await getConfig();
  ownerName = cfg.owner_name;
  const firstName = ownerName.split(" ")[0];

  document.title = `Avatar — ${ownerName}`;
  brandSub.textContent = `${ownerName} · digital twin`;
  introHeading.innerHTML = `I'm ${ownerName}'s <em>digital twin</em>.<br>Ask me anything — and ${firstName} might just chime in.`;
  introBody.textContent = `I know ${ownerName}'s background and the answers to common questions. I can also put you in touch directly.`;
  messageInput.placeholder = `Message ${ownerName}'s twin…  (type "Q2" for an instant answer)`;

  const suggestions = [
    "What do you do for work?",
    "What are you into outside of work?",
    `Can I talk to the real ${firstName}?`,
  ];
  suggestRow.innerHTML = suggestions
    .map((s) => `<button class="chip" type="button">${s}</button>`)
    .join("");
  suggestRow.querySelectorAll<HTMLButtonElement>(".chip").forEach((btn) => {
    btn.addEventListener("click", () => void sendMessage(btn.textContent ?? ""));
  });

  nameInput.value = localStorage.getItem(NAME_STORAGE_KEY) ?? "";

  await initConversation();

  const deepLinkMessage = consumeDeepLinkQuestion();
  if (deepLinkMessage) {
    void sendMessage(deepLinkMessage);
  }

  ensurePolling();
  autoResize();
  messageInput.focus();
}

void init();
