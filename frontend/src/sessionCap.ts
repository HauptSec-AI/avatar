/** Pure timer helpers for the voice session-duration cap (SPEC-VOICE.md). Split
 * out of voiceSession.ts (which also imports the ElevenLabs SDK) so this piece
 * -- a UX safeguard against an accidentally open-ended call, not an abuse
 * defense -- can be tested without a browser or a real voice connection. */

export function scheduleSessionCap(
  maxSessionSeconds: number,
  onCap: () => void,
): ReturnType<typeof setTimeout> {
  return setTimeout(onCap, maxSessionSeconds * 1000);
}

export function clearSessionCap(timer: ReturnType<typeof setTimeout> | undefined): void {
  if (timer !== undefined) clearTimeout(timer);
}
