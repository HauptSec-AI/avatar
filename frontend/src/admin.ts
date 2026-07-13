import "./styles/admin.css";
import {
  AuthError,
  adminListConversations,
  adminLogin,
  adminLogout,
  adminOpenConversation,
  adminPostMessage,
  adminResolveConversation,
  getConversation,
} from "./api";
import { escapeHtml } from "./markdown";
import { formatTime, initials, renderMessageHTML } from "./render";
import { setupThemeToggle } from "./theme";
import type { ConversationSummary, Message } from "./types";

const POLL_MS = 10_000;
type Filter = "all" | "attention" | "unread";

const loginGate = document.getElementById("loginGate") as HTMLDivElement;
const loginForm = document.getElementById("loginForm") as HTMLFormElement;
const passwordInput = document.getElementById("passwordInput") as HTMLInputElement;
const loginError = document.getElementById("loginError") as HTMLParagraphElement;
const dashboardEl = document.getElementById("dashboard") as HTMLDivElement;
const logoutBtn = document.getElementById("logoutBtn") as HTMLButtonElement;
const backBtn = document.getElementById("backBtn") as HTMLButtonElement;

const countBadge = document.getElementById("countBadge") as HTMLSpanElement;
const searchInput = document.getElementById("searchInput") as HTMLInputElement;
const convoListEl = document.getElementById("convoList") as HTMLDivElement;
const filterChips = Array.from(document.querySelectorAll<HTMLSpanElement>(".filter-chip"));
const scanTruncatedBanner = document.getElementById("scanTruncatedBanner") as HTMLDivElement;

const emptyState = document.getElementById("emptyState") as HTMLDivElement;
const threadView = document.getElementById("threadView") as HTMLDivElement;
const threadInitials = document.getElementById("threadInitials") as HTMLSpanElement;
const threadName = document.getElementById("threadName") as HTMLSpanElement;
const threadSub = document.getElementById("threadSub") as HTMLSpanElement;
const attnFlag = document.getElementById("attnFlag") as HTMLSpanElement;
const resolveBtn = document.getElementById("resolveBtn") as HTMLButtonElement;
const threadEl = document.getElementById("thread") as HTMLDivElement;
const threadInnerEl = document.getElementById("threadInner") as HTMLDivElement;
const adminMessageInput = document.getElementById("adminMessageInput") as HTMLTextAreaElement;
const adminSendBtn = document.getElementById("adminSendBtn") as HTMLButtonElement;

let conversations: ConversationSummary[] = [];
let activeConversationId: string | null = null;
let currentThreadRows: Message[] = [];
const renderedThreadIds = new Set<number>();
let filter: Filter = "all";
let searchQuery = "";
let adminSending = false;
let pollTimer: number | undefined;
// Bumped on every openConversation() call so a slower, now-superseded fetch (the
// human clicked a different conversation before this one's request resolved)
// can tell it's stale and skip applying its (wrong-thread) results.
let openConversationToken = 0;

setupThemeToggle("themeToggle");

function applyInboxResult(result: { conversations: ConversationSummary[]; scanTruncated: boolean }): void {
  conversations = result.conversations;
  // scan_truncated: the inbox scan hit INBOX_SCAN_LIMIT, so older conversations
  // (or older activity on one whose only rows are past the cutoff) may be
  // missing -- flag it rather than silently presenting a partial list as complete.
  scanTruncatedBanner.style.display = result.scanTruncated ? "" : "none";
}

function displayName(c: ConversationSummary): string {
  return c.conversation_name || `conv_${c.conversation_id.slice(0, 8)}`;
}

function formatShortTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return "Yest";
  const diffDays = (now.getTime() - d.getTime()) / 86_400_000;
  if (diffDays < 7) return d.toLocaleDateString(undefined, { weekday: "short" });
  return d.toLocaleDateString(undefined, { month: "numeric", day: "numeric" });
}

function matchesFilter(c: ConversationSummary): boolean {
  if (filter === "attention" && !c.needs_attention) return false;
  if (filter === "unread" && !c.unread) return false;
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    return displayName(c).toLowerCase().includes(q) || c.preview.toLowerCase().includes(q);
  }
  return true;
}

function convoItemHTML(c: ConversationSummary, isActive: boolean): string {
  const classes = ["convo-item"];
  if (isActive) classes.push("is-active");
  if (c.unread) classes.push("is-unread");
  if (c.needs_attention) classes.push("is-attention");
  const badge = c.needs_attention
    ? `<span class="badge badge--attention"><svg class="icon" style="width:11px;height:11px"><use href="/icons.svg#i-spark"/></svg> Needs you</span>`
    : c.unread
      ? `<span class="badge badge--dot"></span>`
      : `<svg class="icon icon--sm" style="color:var(--positive)"><use href="/icons.svg#i-check2"/></svg>`;
  return `<div class="${classes.join(" ")}" data-id="${c.conversation_id}">
    <span class="avatar-initials">${initials(displayName(c))}</span>
    <div class="convo-main">
      <div class="convo-top"><span class="convo-name">${escapeHtml(displayName(c))}</span></div>
      <div class="convo-preview">${escapeHtml(c.preview)}</div>
    </div>
    <div class="convo-side">
      <span class="msg-time">${formatShortTime(c.last_message_at)}</span>
      ${badge}
    </div>
  </div>`;
}

function renderSidebar(): void {
  const filtered = conversations.filter(matchesFilter);
  countBadge.textContent = String(conversations.length);
  convoListEl.innerHTML = filtered.length
    ? filtered.map((c) => convoItemHTML(c, c.conversation_id === activeConversationId)).join("")
    : `<div class="convo-empty">No conversations${searchQuery ? " match your search" : " yet"}.</div>`;
  convoListEl.querySelectorAll<HTMLDivElement>(".convo-item").forEach((el) => {
    el.addEventListener("click", () => void openConversation(el.dataset.id as string));
  });

  const attnCount = conversations.filter((c) => c.needs_attention).length;
  const unreadCount = conversations.filter((c) => c.unread).length;
  for (const chip of filterChips) {
    if (chip.dataset.filter === "attention") {
      chip.innerHTML = `<span class="dot-y"></span>Needs you · ${attnCount}`;
    } else if (chip.dataset.filter === "unread") {
      chip.textContent = `Unread · ${unreadCount}`;
    }
  }
}

function currentVisitorName(): string | null {
  return conversations.find((c) => c.conversation_id === activeConversationId)?.conversation_name ?? null;
}

function humanTagHtmlAdmin(): string {
  return `<span class="human-tag"><svg class="icon"><use href="/icons.svg#i-live"/></svg> You · sent to visitor</span>`;
}

function updateAttnFlag(): void {
  attnFlag.style.display = currentThreadRows.some((r) => r.needs_attention) ? "" : "none";
}

function appendThreadRows(rows: Message[]): void {
  const visitorLabel = initials(currentVisitorName());
  for (const row of rows) {
    if (renderedThreadIds.has(row.id)) continue;
    renderedThreadIds.add(row.id);
    currentThreadRows.push(row);
    const wrapper = document.createElement("div");
    wrapper.innerHTML = renderMessageHTML(row, {
      humanTagHtml: humanTagHtmlAdmin(),
      visitorInitials: visitorLabel,
    });
    threadInnerEl.appendChild(wrapper.firstElementChild!);
  }
  threadEl.scrollTop = threadEl.scrollHeight;
  updateAttnFlag();
}

function renderThreadHeader(id: string): void {
  const summary = conversations.find((c) => c.conversation_id === id);
  const name = summary ? displayName(summary) : `conv_${id.slice(0, 8)}`;
  threadInitials.textContent = initials(name);
  threadName.textContent = name;
  const startedAt = currentThreadRows[0] ? formatTime(currentThreadRows[0].created_at) : "—";
  threadSub.textContent = `conv_${id.slice(0, 8)} · started ${startedAt} · ${currentThreadRows.length} messages`;
}

async function openConversation(id: string): Promise<void> {
  const myToken = ++openConversationToken;
  activeConversationId = id;
  renderedThreadIds.clear();
  currentThreadRows = [];
  threadInnerEl.innerHTML = `<div class="thread-loading">Loading…</div>`;
  emptyState.style.display = "none";
  threadView.style.display = "flex";
  document.body.classList.add("detail-open");
  renderSidebar();

  try {
    const rows = await adminOpenConversation(id);
    if (myToken !== openConversationToken) return; // superseded by a newer click
    const summary = conversations.find((c) => c.conversation_id === id);
    if (summary) {
      summary.unread = false;
      summary.needs_attention = false;
    }
    threadInnerEl.innerHTML = "";
    appendThreadRows(rows);
    renderThreadHeader(id);
    renderSidebar();
    adminMessageInput.focus();
  } catch (e) {
    if (myToken !== openConversationToken) return;
    if (e instanceof AuthError) return showLoginGate();
    throw e;
  }
}

function autoResizeAdmin(): void {
  adminMessageInput.style.height = "auto";
  adminMessageInput.style.height = `${Math.min(adminMessageInput.scrollHeight, 160)}px`;
}

function setAdminComposerEnabled(enabled: boolean): void {
  adminMessageInput.disabled = !enabled;
  adminSendBtn.disabled = !enabled;
}

async function sendAdminMessage(): Promise<void> {
  const text = adminMessageInput.value.trim();
  if (!text || !activeConversationId || adminSending) return;
  adminSending = true;
  setAdminComposerEnabled(false);
  adminMessageInput.value = "";
  autoResizeAdmin();

  try {
    const row = await adminPostMessage(activeConversationId, text);
    appendThreadRows([row]);
    const summary = conversations.find((c) => c.conversation_id === activeConversationId);
    if (summary) {
      summary.preview = row.content;
      summary.last_message_at = row.created_at;
      summary.last_role = "human";
    }
    renderSidebar();
  } catch (e) {
    if (e instanceof AuthError) {
      showLoginGate();
      return;
    }
  }
  adminSending = false;
  setAdminComposerEnabled(true);
  adminMessageInput.focus();
}

adminMessageInput.addEventListener("input", autoResizeAdmin);
adminMessageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    void sendAdminMessage();
  }
});
adminSendBtn.addEventListener("click", () => void sendAdminMessage());

resolveBtn.addEventListener("click", async () => {
  if (!activeConversationId) return;
  try {
    await adminResolveConversation(activeConversationId);
  } catch (e) {
    if (e instanceof AuthError) return showLoginGate();
  }
  currentThreadRows.forEach((r) => {
    r.needs_attention = false;
  });
  updateAttnFlag();
  const summary = conversations.find((c) => c.conversation_id === activeConversationId);
  if (summary) summary.needs_attention = false;
  renderSidebar();
});

backBtn.addEventListener("click", () => {
  document.body.classList.remove("detail-open");
});

filterChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    filter = (chip.dataset.filter as Filter) ?? "all";
    filterChips.forEach((c) => c.classList.toggle("is-on", c === chip));
    renderSidebar();
  });
});

searchInput.addEventListener("input", () => {
  searchQuery = searchInput.value.trim();
  renderSidebar();
});

document.addEventListener("keydown", (e) => {
  const active = document.activeElement;
  if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) return;
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const filtered = conversations.filter(matchesFilter);
  if (!filtered.length) return;
  e.preventDefault();
  const idx = filtered.findIndex((c) => c.conversation_id === activeConversationId);
  const nextIdx =
    e.key === "ArrowDown"
      ? idx === -1
        ? 0
        : Math.min(idx + 1, filtered.length - 1)
      : idx === -1
        ? 0
        : Math.max(idx - 1, 0);
  void openConversation(filtered[nextIdx]!.conversation_id);
});

// ---- auth / bootstrapping ----

function showLoginGate(): void {
  stopPolling();
  document.body.classList.add("login-active");
  document.body.classList.remove("detail-open");
  loginGate.style.display = "flex";
  dashboardEl.style.display = "none";
  window.setTimeout(() => passwordInput.focus(), 0);
}

function enterDashboard(): void {
  document.body.classList.remove("login-active");
  loginGate.style.display = "none";
  dashboardEl.style.display = "grid";
  renderSidebar();
  startPolling();
}

async function pollTick(): Promise<void> {
  if (document.hidden) return;
  try {
    applyInboxResult(await adminListConversations());
  } catch (e) {
    if (e instanceof AuthError) showLoginGate();
    return;
  }
  renderSidebar();
  if (activeConversationId) {
    // Read-only refresh -- adminOpenConversation() also marks read + clears
    // needs_attention, which is correct for a deliberate click but wrong here: a
    // poll tick firing right after a new flagged message arrives would silently
    // clear the flag before the human actually notices (RECS.md).
    const polledConversationId = activeConversationId;
    try {
      const rows = await getConversation(polledConversationId);
      if (polledConversationId !== activeConversationId) return; // switched threads mid-poll
      appendThreadRows(rows);
      renderThreadHeader(polledConversationId);
    } catch {
      // transient; retry next tick
    }
  }
}

function startPolling(): void {
  if (pollTimer !== undefined) return;
  pollTimer = window.setInterval(() => void pollTick(), POLL_MS);
}

function stopPolling(): void {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer);
    pollTimer = undefined;
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.style.display = "none";
  const ok = await adminLogin(passwordInput.value);
  passwordInput.value = "";
  if (!ok) {
    loginError.textContent = "Incorrect password. Please try again.";
    loginError.style.display = "";
    passwordInput.focus();
    return;
  }
  try {
    applyInboxResult(await adminListConversations());
  } catch {
    conversations = [];
  }
  enterDashboard();
});

logoutBtn.addEventListener("click", async () => {
  await adminLogout();
  showLoginGate();
});

async function boot(): Promise<void> {
  try {
    applyInboxResult(await adminListConversations());
  } catch (e) {
    if (e instanceof AuthError) {
      showLoginGate();
      return;
    }
    throw e;
  }
  enterDashboard();
}

void boot();
