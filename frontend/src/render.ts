import { renderMarkdown } from "./markdown";
import type { Message } from "./types";

export function initials(name: string | null | undefined): string {
  if (!name) return "You";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "You";
  return parts
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export interface RenderOptions {
  /** Full inner HTML for the human-role tag; differs between visitor and admin views. */
  humanTagHtml: string;
  visitorInitials: string;
}

export function instantTagHtml(row: Message): string {
  if (row.role !== "avatar") return "";
  const match = row.content.match(/^\*\*Q(\d+):\*\*/);
  return match ? `<span class="instant-tag">instant · Q${match[1]}</span>` : "";
}

export function channelTagHtml(row: Message): string {
  if (row.channel !== "voice") return "";
  return `<span class="channel-tag" title="Spoken during a voice call"><svg class="icon"><use href="/icons.svg#i-mic"/></svg></span>`;
}

export function renderMessageHTML(row: Message, opts: RenderOptions): string {
  const time = formatTime(row.created_at);
  const bubble = `<div class="bubble">${renderMarkdown(row.content)}</div>`;

  if (row.role === "visitor") {
    return `<div class="msg msg--visitor" data-id="${row.id}">
      <span class="avatar-initials">${opts.visitorInitials}</span>
      <div class="msg-body">
        <div class="msg-meta">${channelTagHtml(row)}<span class="msg-time">${time}</span></div>
        ${bubble}
      </div>
    </div>`;
  }

  if (row.role === "human") {
    return `<div class="msg msg--human" data-id="${row.id}">
      <div class="avatar avatar-human" style="background-image:url('/assets/avatar-human.png')">
        <span class="spark-badge"><svg class="icon"><use href="/icons.svg#i-spark"/></svg></span>
      </div>
      <div class="msg-body">
        <div class="msg-meta">${opts.humanTagHtml}${channelTagHtml(row)}<span class="msg-time">${time}</span></div>
        ${bubble}
      </div>
    </div>`;
  }

  return `<div class="msg msg--avatar" data-id="${row.id}">
    <div class="avatar avatar-twin" style="background-image:url('/assets/avatar-robot-round.png')"></div>
    <div class="msg-body">
      <div class="msg-meta"><span class="msg-name">Avatar</span>${instantTagHtml(row)}${channelTagHtml(row)}<span class="msg-time">${time}</span></div>
      ${bubble}
    </div>
  </div>`;
}
