import { escapeHtml } from "./markdown";
import { startVoiceCall, type CallMode, type CallStatus, type VoiceCallHandle } from "./voiceSession";

const VISUALIZER_BAR_COUNT = 28;

function voicePanelHTML(): string {
  return `
    <div class="voice-panel" id="voicePanel" data-status="connecting" data-mode="listening">
      <div class="voice-visualizer" id="voiceVisualizer"></div>
      <div class="voice-status" id="voiceStatus"><span class="dot"></span><span id="voiceStatusText">Connecting…</span></div>
      <div class="voice-captions scroll" id="voiceCaptions"></div>
      <div class="voice-controls">
        <button class="icon-btn voice-mute-btn" id="voiceMuteBtn" title="Mute microphone">
          <svg class="icon"><use href="/icons.svg#i-mic"/></svg>
        </button>
        <button class="btn voice-end-btn" id="voiceEndBtn">End call</button>
      </div>
    </div>`;
}

const STATUS_LABEL: Record<CallStatus, string> = {
  connecting: "Connecting…",
  connected: "Connected",
  disconnecting: "Ending…",
  disconnected: "Call ended",
};

export interface MountedVoiceCall {
  teardown: () => void;
}

export interface MountVoiceCallOptions {
  onStatusChange?: (status: CallStatus) => void;
  /** Called when the visitor explicitly dismisses an ended/failed call (clicks
   * "Back to chat"). NOT called automatically on disconnect -- an immediate
   * connection failure needs to stay on screen long enough to read the error,
   * so only a deliberate click closes the panel. */
  onClose?: () => void;
}

/**
 * Mounts a live voice call into `root`: builds the panel, starts the ElevenLabs
 * session, and wires the visualizer/captions/controls to it. Used by both the
 * dedicated /voice page and the inline launcher on the main chat page.
 */
export async function mountVoiceCall(
  root: HTMLElement,
  conversationId: string,
  options: MountVoiceCallOptions = {},
): Promise<MountedVoiceCall> {
  const { onStatusChange, onClose } = options;
  root.innerHTML = voicePanelHTML();
  const panel = root.querySelector<HTMLDivElement>("#voicePanel")!;
  const visualizerEl = root.querySelector<HTMLDivElement>("#voiceVisualizer")!;
  const statusTextEl = root.querySelector<HTMLSpanElement>("#voiceStatusText")!;
  const captionsEl = root.querySelector<HTMLDivElement>("#voiceCaptions")!;
  const muteBtn = root.querySelector<HTMLButtonElement>("#voiceMuteBtn")!;
  const endBtn = root.querySelector<HTMLButtonElement>("#voiceEndBtn")!;

  const bars: HTMLDivElement[] = [];
  for (let i = 0; i < VISUALIZER_BAR_COUNT; i++) {
    const bar = document.createElement("div");
    bar.className = "voice-bar";
    visualizerEl.appendChild(bar);
    bars.push(bar);
  }

  let handle: VoiceCallHandle | null = null;
  let rafId: number | undefined;

  function setStatus(status: CallStatus): void {
    panel.dataset.status = status;
    statusTextEl.textContent = STATUS_LABEL[status];
    endBtn.textContent = status === "disconnected" ? "Back to chat" : "End call";
    onStatusChange?.(status);
  }

  function setMode(mode: CallMode): void {
    panel.dataset.mode = mode;
  }

  function appendCaption(role: "visitor" | "avatar", text: string): void {
    const line = document.createElement("div");
    line.className = `voice-caption-line voice-caption-line--${role}`;
    line.innerHTML = `<span class="voice-caption-role">${role === "visitor" ? "You" : "Avatar"}</span>${escapeHtml(text)}`;
    captionsEl.appendChild(line);
    captionsEl.scrollTop = captionsEl.scrollHeight;
  }

  const toolStatusEls = new Map<string, HTMLDivElement>();
  const TOOL_LABELS: Record<string, { calling: string; done: string }> = {
    faq_tool: { calling: "Looking up the FAQ…", done: "Looked up the FAQ" },
    push_tool: { calling: "Notifying the human…", done: "Notified the human" },
  };

  function appendToolStatus(name: string, status: "called" | "done"): void {
    const label = TOOL_LABELS[name] ?? { calling: `Calling ${name}…`, done: name };
    let el = toolStatusEls.get(name);
    if (!el) {
      el = document.createElement("div");
      el.className = "voice-tool-status";
      captionsEl.appendChild(el);
      toolStatusEls.set(name, el);
    }
    const done = status === "done";
    el.classList.toggle("is-done", done);
    const icon = done ? "i-check" : "i-tool";
    el.innerHTML = `<svg class="icon"><use href="/icons.svg#${icon}"/></svg> ${done ? label.done : label.calling}`;
    captionsEl.scrollTop = captionsEl.scrollHeight;
  }

  function showError(message: string): void {
    const banner = document.createElement("div");
    banner.className = "banner";
    banner.textContent = message;
    captionsEl.appendChild(banner);
    captionsEl.scrollTop = captionsEl.scrollHeight;
  }

  function drawVisualizer(): void {
    if (handle) {
      const speaking = panel.dataset.mode === "speaking";
      const data = speaking ? handle.getOutputByteFrequencyData() : handle.getInputByteFrequencyData();
      const bucket = Math.max(1, Math.floor(data.length / bars.length));
      for (let i = 0; i < bars.length; i++) {
        const v = data[i * bucket] ?? 0;
        bars[i]!.style.height = `${Math.max(3, (v / 255) * 90)}px`;
      }
    }
    rafId = requestAnimationFrame(drawVisualizer);
  }

  setStatus("connecting");
  rafId = requestAnimationFrame(drawVisualizer);

  try {
    handle = await startVoiceCall(conversationId, {
      onStatusChange: setStatus,
      onModeChange: setMode,
      onTranscript: ({ role, text }) => appendCaption(role, text),
      onToolStatus: appendToolStatus,
      onError: showError,
    });
  } catch {
    setStatus("disconnected");
  }

  muteBtn.addEventListener("click", () => {
    if (!handle) return;
    const muted = handle.toggleMute();
    muteBtn.classList.toggle("is-muted", muted);
    muteBtn.innerHTML = `<svg class="icon"><use href="/icons.svg#${muted ? "i-mic-off" : "i-mic"}"/></svg>`;
  });

  endBtn.addEventListener("click", () => {
    if (panel.dataset.status === "disconnected") {
      onClose?.();
    } else {
      void handle?.endCall();
    }
  });

  function teardown(): void {
    if (rafId !== undefined) cancelAnimationFrame(rafId);
    void handle?.endCall();
  }

  return { teardown };
}
