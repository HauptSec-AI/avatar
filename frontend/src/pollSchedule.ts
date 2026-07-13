/** Pure poll-interval logic for the human-message poll (SPEC-AVATAR.md: "10s,
 * slowing to 60s after 5 idle minutes"). Split out of chat.ts -- which also does
 * DOM setup at import time -- so this can be tested without a browser. */

export const POLL_FAST_MS = 10_000;
export const POLL_SLOW_MS = 60_000;
export const POLL_SLOWDOWN_AFTER_MS = 5 * 60_000;

export function pollIntervalMs(idleMs: number): number {
  return idleMs > POLL_SLOWDOWN_AFTER_MS ? POLL_SLOW_MS : POLL_FAST_MS;
}
