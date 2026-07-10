import { test, expect, type Page } from "@playwright/test";
import { loadRootEnv } from "./helpers";

const ADMIN_PASSWORD = loadRootEnv().ADMIN_PASSWORD!;

// Voice tests deliberately never drive a full, successful ElevenLabs connection --
// that would consume real per-minute call time on a live account (SPEC-VOICE.md
// reserves that for a deliberate manual smoke test, not the routine suite). What's
// covered instead: static UI/theme/responsive rendering (no network calls), the
// real-but-free error path (a real POST /api/voice/session token mint, then a real
// failed WebRTC handshake since Playwright's default context has no mic permission
// granted -- getUserMedia rejects before anything billable happens), the session-mint
// rate limit, and the admin mic-badge rendering (mocked responses, no backend hit).
// Assertions only check that *some* banner/error appears, not its exact text, so
// these pass whether or not ELEVENLABS_* is actually configured in .env.

async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto("/admin");
  await page.fill("#passwordInput", ADMIN_PASSWORD);
  await page.click('#loginForm button[type="submit"]');
  await expect(page.locator("#dashboard")).toBeVisible();
}

test.describe("Voice", () => {
  test("voice page: hero, theme toggle, and controls render", async ({ page }, testInfo) => {
    await page.goto("/voice");
    await expect(page.locator("#heroHeading")).toContainText("digital twin");
    await expect(page.locator("#startCallBtn")).toBeVisible();
    await expect(page.locator(".voice-switch-hint")).toBeVisible();
    await expect(page.locator("#keepChatToggle")).toBeChecked();
    await expect(page.locator("#nameInput")).toBeVisible();
    await expect(page.locator("#resetBtn")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({
      path: `screenshots/visitor/voice-01-hero-dark-${testInfo.project.name}.png`,
      fullPage: true,
    });

    await page.click("#themeToggle");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.screenshot({
      path: `screenshots/visitor/voice-02-hero-light-${testInfo.project.name}.png`,
      fullPage: true,
    });
  });

  test("voice page: starting a call without mic permission shows a dismissible error", async ({
    page,
  }, testInfo) => {
    await page.goto("/voice");
    await page.click("#startCallBtn");
    await expect(page.locator("#voiceHero")).toBeHidden();
    await expect(page.locator("#voicePanel")).toBeVisible();

    await expect(page.locator(".banner")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("#voiceEndBtn")).toHaveText("Back to chat");
    await page.screenshot({
      path: `screenshots/visitor/voice-03-error-${testInfo.project.name}.png`,
      fullPage: true,
    });

    await page.click("#voiceEndBtn");
    await expect(page.locator("#voiceHero")).toBeVisible();
    await expect(page.locator("#voicePanelRoot")).toBeHidden();
  });

  test("voice page: Reset tears down an active call and starts a fresh conversation_id", async ({
    page,
  }) => {
    await page.goto("/voice");
    const before = await page.evaluate(() => document.cookie.match(/avatar_conversation_id=([^;]+)/)?.[1]);

    await page.click("#startCallBtn");
    await expect(page.locator("#voicePanel")).toBeVisible();
    await page.click("#resetBtn");

    await expect(page.locator("#voiceHero")).toBeVisible();
    const after = await page.evaluate(() => document.cookie.match(/avatar_conversation_id=([^;]+)/)?.[1]);
    expect(after).toBeTruthy();
    expect(after).not.toBe(before);
  });

  test("inline voice launcher on the main chat page swaps the composer and back again", async ({
    page,
  }, testInfo) => {
    await page.goto("/");
    await expect(page.locator("#voiceLaunchBtn")).toBeVisible();
    await page.click("#voiceLaunchBtn");
    await expect(page.locator("#textComposerWrap")).toBeHidden();
    await expect(page.locator("#voicePanel")).toBeVisible();
    await page.screenshot({
      path: `screenshots/visitor/voice-04-inline-${testInfo.project.name}.png`,
      fullPage: true,
    });

    await expect(page.locator(".banner")).toBeVisible({ timeout: 15_000 });
    await page.click("#voiceEndBtn");
    await expect(page.locator("#textComposerWrap")).toBeVisible();
    await expect(page.locator("#voiceInlineWrap")).toBeHidden();
    await expect(page.locator("#messageInput")).toBeFocused();
  });

  test("voice session minting is rate limited after 5 calls/minute for one conversation_id", async ({
    request,
  }) => {
    const conversationId = crypto.randomUUID();
    for (let i = 0; i < 5; i++) {
      const resp = await request.post("/api/voice/session", { data: { conversation_id: conversationId } });
      // 200 if ELEVENLABS_* is configured and the real API call succeeds, 503 if
      // voice isn't configured, 502 if a real call to ElevenLabs fails (e.g. rate
      // limited on their side from 5 rapid mints) -- either way the rate limiter
      // (which runs before the ElevenLabs call) should have counted the request.
      expect([200, 502, 503]).toContain(resp.status());
    }
    const blocked = await request.post("/api/voice/session", { data: { conversation_id: conversationId } });
    expect(blocked.status()).toBe(429);
    expect((await blocked.json()).error.toLowerCase()).toContain("quickly");
  });

  test("voice session rejects an invalid conversation_id", async ({ request }) => {
    const resp = await request.post("/api/voice/session", { data: { conversation_id: "not-a-uuid" } });
    expect(resp.status()).toBe(400);
  });

  test("admin: a voice-channel message shows a mic badge", async ({ page }) => {
    const conversationId = crypto.randomUUID();
    const nowIso = new Date().toISOString();
    const summary = {
      conversation_id: conversationId,
      conversation_name: "Voice Badge Test",
      preview: "Hi from a call",
      last_role: "visitor",
      last_message_at: nowIso,
      message_count: 1,
      unread: false,
      needs_attention: false,
    };
    const detail = {
      conversation_id: conversationId,
      messages: [
        {
          id: 1,
          conversation_id: conversationId,
          conversation_name: "Voice Badge Test",
          role: "visitor",
          content: "Hi from a call",
          tool_calls: null,
          needs_attention: false,
          read: true,
          channel: "voice",
          created_at: nowIso,
        },
      ],
    };

    await loginAsAdmin(page);
    await page.route("**/admin/conversations", (route) =>
      route.request().method() === "GET"
        ? route.fulfill({ json: { conversations: [summary] } })
        : route.continue(),
    );
    await page.route(`**/admin/conversations/${conversationId}`, (route) => route.fulfill({ json: detail }));

    await page.reload();
    await page.locator(".convo-item").first().click();
    await expect(page.locator(".channel-tag")).toBeVisible();
    await expect(page.locator(".channel-tag")).toHaveAttribute("title", /voice call/i);
  });
});
