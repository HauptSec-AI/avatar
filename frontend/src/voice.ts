import "./styles/voice.css";
import { getConfig } from "./api";
import { deleteCookie, getCookie, setCookie } from "./cookies";
import { setupThemeToggle } from "./theme";
import { mountVoiceCall, type MountedVoiceCall } from "./voiceUI";

const COOKIE_NAME = "avatar_conversation_id";
const NAME_STORAGE_KEY = "avatar-name";

const nameInput = document.getElementById("nameInput") as HTMLInputElement;
const keepChatToggle = document.getElementById("keepChatToggle") as HTMLInputElement;
const resetBtn = document.getElementById("resetBtn") as HTMLButtonElement;
const brandSub = document.getElementById("brandSub") as HTMLDivElement;
const heroHeading = document.getElementById("heroHeading") as HTMLHeadingElement;
const heroBody = document.getElementById("heroBody") as HTMLParagraphElement;
const startBtn = document.getElementById("startCallBtn") as HTMLButtonElement;
const heroEl = document.getElementById("voiceHero") as HTMLDivElement;
const panelRoot = document.getElementById("voicePanelRoot") as HTMLDivElement;

let conversationId = "";
let mounted: MountedVoiceCall | null = null;

setupThemeToggle("themeToggle");

function newConversationId(): string {
  return crypto.randomUUID();
}

function showHero(): void {
  heroEl.style.display = "";
  panelRoot.style.display = "none";
  panelRoot.innerHTML = "";
}

async function startCall(): Promise<void> {
  heroEl.style.display = "none";
  panelRoot.style.display = "";
  mounted = await mountVoiceCall(panelRoot, conversationId, {
    onClose: () => {
      mounted = null;
      showHero();
    },
  });
}

startBtn.addEventListener("click", () => void startCall());

keepChatToggle.addEventListener("change", () => {
  if (keepChatToggle.checked) setCookie(COOKIE_NAME, conversationId);
  else deleteCookie(COOKIE_NAME);
});

resetBtn.addEventListener("click", () => {
  mounted?.teardown();
  mounted = null;
  conversationId = newConversationId();
  if (keepChatToggle.checked) setCookie(COOKIE_NAME, conversationId);
  else deleteCookie(COOKIE_NAME);
  showHero();
});

nameInput.addEventListener("input", () => localStorage.setItem(NAME_STORAGE_KEY, nameInput.value));

async function init(): Promise<void> {
  const cfg = await getConfig();
  const ownerName = cfg.owner_name;
  const firstName = ownerName.split(" ")[0];

  document.title = `Talk to ${ownerName} — Avatar`;
  brandSub.textContent = `${ownerName} · digital twin`;
  heroHeading.innerHTML = `Talk to my <em>digital twin</em>.`;
  heroBody.textContent = `Speak with ${ownerName}'s twin, in ${firstName}'s own voice — and ${firstName} might just chime in.`;

  nameInput.value = localStorage.getItem(NAME_STORAGE_KEY) ?? "";

  // Same conversation_id (and Keep-chat semantics) as text chat, so a visitor's
  // spoken and typed turns land in one unified admin thread. See SPEC-VOICE.md.
  const existing = keepChatToggle.checked ? getCookie(COOKIE_NAME) : null;
  if (existing) {
    conversationId = existing;
  } else {
    conversationId = newConversationId();
    if (keepChatToggle.checked) setCookie(COOKIE_NAME, conversationId);
  }
}

void init();
