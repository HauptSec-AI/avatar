// Minimal, safe markdown for chat bubbles: paragraphs, links, bold — exactly what
// components.css styles (.bubble p / a / strong) and knowledge/PERSONALITY.md asks for
// ("no code blocks"). Deliberately not a general-purpose renderer.

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g;
const BOLD_RE = /\*\*([^*]+)\*\*/g;

function inline(text: string): string {
  const escaped = escapeHtml(text);
  const linked = escaped.replace(
    LINK_RE,
    (_m, label: string, url: string) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`,
  );
  return linked.replace(BOLD_RE, (_m, inner: string) => `<strong>${inner}</strong>`);
}

export function renderMarkdown(text: string): string {
  const paragraphs = text.trim().split(/\n{2,}/);
  return paragraphs.map((p) => `<p>${inline(p).replace(/\n/g, "<br>")}</p>`).join("");
}
