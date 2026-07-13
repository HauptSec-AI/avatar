import { VoiceConversation } from "@elevenlabs/client";
import { notifyVoiceSessionStarted, startVoiceSession, VoiceSessionError } from "./api";
import { clearSessionCap, scheduleSessionCap } from "./sessionCap";

export type CallStatus = "connecting" | "connected" | "disconnecting" | "disconnected";
export type CallMode = "speaking" | "listening";

export interface VoiceCallCallbacks {
  onStatusChange: (status: CallStatus) => void;
  onModeChange: (mode: CallMode) => void;
  onTranscript: (props: { role: "visitor" | "avatar"; text: string }) => void;
  onToolStatus: (name: string, status: "called" | "done") => void;
  onError: (message: string) => void;
}

export interface VoiceCallHandle {
  endCall: () => Promise<void>;
  toggleMute: () => boolean;
  isMuted: () => boolean;
  getInputVolume: () => number;
  getOutputVolume: () => number;
  getInputByteFrequencyData: () => Uint8Array;
  getOutputByteFrequencyData: () => Uint8Array;
}

/**
 * Starts a live voice call: mints a connection credential from our backend, opens
 * the ElevenLabs WebRTC session directly (no per-token hop through our server),
 * and registers the {ourConversationId, elevenlabsConversationId} mapping the
 * moment the SDK confirms a connection -- before any spoken turn -- so tool
 * webhooks and the post-call transcript webhook can find their way back to this
 * conversation. See SPEC-VOICE.md.
 */
export async function startVoiceCall(
  conversationId: string,
  callbacks: VoiceCallCallbacks,
): Promise<VoiceCallHandle> {
  let session: { token: string; agentId: string; maxSessionSeconds: number; sessionNonce: string };
  try {
    session = await startVoiceSession(conversationId);
  } catch (e) {
    const message = e instanceof VoiceSessionError ? e.message : "Couldn't start a voice session.";
    callbacks.onError(message);
    throw e;
  }

  let muted = false;
  let sessionCapTimer: ReturnType<typeof setTimeout> | undefined;
  let conversation: Awaited<ReturnType<typeof VoiceConversation.startSession>>;

  try {
    conversation = await VoiceConversation.startSession({
      conversationToken: session.token,
      connectionType: "webrtc",
      // Our own conversation_id, not ElevenLabs'. Interpolated into the tool webhook
      // request bodies (see backend/app/voice.py build_agent_config) so faq_tool and
      // push_tool always know which thread they're part of, with no lookup needed.
      dynamicVariables: { conversation_id: conversationId },
      onConnect: ({ conversationId: elevenlabsConversationId }) => {
        void notifyVoiceSessionStarted(conversationId, elevenlabsConversationId, session.sessionNonce);
        // Client-side session-length cap: a UX safeguard against an accidentally
        // open-ended call, not an abuse defense -- our backend isn't in the media
        // path, so it can't forcibly end a live ElevenLabs session. The real abuse
        // backstops are the same as text chat: rate-limited session minting
        // (/api/voice/session) and ElevenLabs' own account-level spend/concurrency
        // caps (see SPEC-VOICE.md).
        sessionCapTimer = scheduleSessionCap(session.maxSessionSeconds, () => {
          void conversation?.endSession();
        });
      },
      onStatusChange: ({ status }) => callbacks.onStatusChange(status),
      onModeChange: ({ mode }) => callbacks.onModeChange(mode),
      onMessage: ({ message, role }) => {
        callbacks.onTranscript({ role: role === "user" ? "visitor" : "avatar", text: message });
      },
      onAgentToolRequest: (props) => callbacks.onToolStatus(props.tool_name, "called"),
      onAgentToolResponse: (props) => callbacks.onToolStatus(props.tool_name, "done"),
      onError: (message) => callbacks.onError(message),
      onDisconnect: () => {
        clearSessionCap(sessionCapTimer);
      },
    });
  } catch (e) {
    // Most commonly a denied/unavailable microphone (getUserMedia rejects before
    // the SDK ever calls its own onError) -- without this, the caller only sees a
    // silent "disconnected" status with no explanation of what went wrong.
    const message = e instanceof Error ? e.message : "Couldn't connect. Check your microphone permission and try again.";
    callbacks.onError(message);
    throw e;
  }

  return {
    endCall: () => conversation.endSession(),
    toggleMute: () => {
      muted = !muted;
      conversation.setMicMuted(muted);
      return muted;
    },
    isMuted: () => muted,
    getInputVolume: () => conversation.getInputVolume(),
    getOutputVolume: () => conversation.getOutputVolume(),
    getInputByteFrequencyData: () => conversation.getInputByteFrequencyData(),
    getOutputByteFrequencyData: () => conversation.getOutputByteFrequencyData(),
  };
}
