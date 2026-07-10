import { test, expect } from "@playwright/test";

const SHOT = (name: string, project: string) => `screenshots/visitor/${name}-${project}.png`;

test.describe("Visitor chat", () => {
  test("intro state, focus, theme toggle, responsive", async ({ page }, testInfo) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Avatar/);

    const composer = page.locator("#messageInput");
    await expect(composer).toBeFocused();
    await expect(page.locator("#intro")).toBeVisible();
    await expect(page.locator("#suggestRow .chip")).toHaveCount(3);

    // dark is default
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({ path: SHOT("01-intro-dark", testInfo.project.name), fullPage: true });

    // toggle to light
    await page.click("#themeToggle");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.screenshot({ path: SHOT("02-intro-light", testInfo.project.name), fullPage: true });

    // toggle back to dark for the rest of the suite
    await page.click("#themeToggle");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  test("Qn instant answer shortcut, no LLM call, tagged", async ({ page }, testInfo) => {
    await page.goto("/");
    await page.fill("#messageInput", "Q2");
    await page.keyboard.press("Enter");

    const avatarMsg = page.locator(".msg--avatar").first();
    await expect(avatarMsg).toBeVisible({ timeout: 10_000 });
    await expect(avatarMsg.locator(".instant-tag")).toHaveText(/instant · Q2/);
    await expect(page.locator(".msg--visitor").first()).toBeVisible();
    await expect(composerFocused(page)).resolves.toBe(true);
    await page.screenshot({ path: SHOT("03-qn-instant", testInfo.project.name), fullPage: true });
  });

  test("deep link ?q=N auto-submits and clears the query param", async ({ page }, testInfo) => {
    await page.goto("/?q=1");
    const avatarMsg = page.locator(".msg--avatar").first();
    await expect(avatarMsg).toBeVisible({ timeout: 10_000 });
    await expect(avatarMsg.locator(".instant-tag")).toHaveText(/instant · Q1/);
    await expect(page).toHaveURL(/\/(\?)?$/);
    await page.screenshot({ path: SHOT("04-deep-link-q1", testInfo.project.name), fullPage: true });
  });

  test("suggestion chip submits immediately", async ({ page }) => {
    await page.goto("/");
    const chip = page.locator("#suggestRow .chip").first();
    const chipText = await chip.textContent();
    await chip.click();
    await expect(page.locator(".msg--visitor").first()).toContainText(chipText!.trim());
  });

  test("normal message streams a real reply and composer re-focuses", async ({ page }, testInfo) => {
    await page.goto("/");
    await page.fill("#messageInput", "In one short sentence, what is RAG?");
    await page.keyboard.press("Enter");

    await expect(page.locator(".msg--visitor").first()).toBeVisible();
    const avatarMsg = page.locator(".msg--avatar").first();
    await expect(avatarMsg).toBeVisible({ timeout: 20_000 });
    await expect(avatarMsg.locator(".bubble")).not.toHaveText("", { timeout: 20_000 });
    // composer re-enabled + refocused once the stream completes
    await expect(page.locator("#messageInput")).toBeEnabled({ timeout: 20_000 });
    await expect(composerFocused(page)).resolves.toBe(true);
    await page.screenshot({ path: SHOT("05-real-reply", testInfo.project.name), fullPage: true });
  });

  test("Keep chat: reload restores the conversation from cookie", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#keepChatToggle")).toBeChecked();
    await page.fill("#messageInput", "Q3");
    await page.keyboard.press("Enter");
    await expect(page.locator(".msg--avatar").first()).toBeVisible({ timeout: 10_000 });

    await page.reload();
    await expect(page.locator(".msg--visitor").first()).toBeVisible();
    await expect(page.locator(".msg--avatar").first()).toBeVisible();
    await expect(page.locator("#intro")).toBeHidden();
  });

  test("Reset issues a fresh conversation and clears the thread", async ({ page }) => {
    await page.goto("/");
    await page.fill("#messageInput", "Q4");
    await page.keyboard.press("Enter");
    await expect(page.locator(".msg--avatar").first()).toBeVisible({ timeout: 10_000 });

    await page.click("#resetBtn");
    await expect(page.locator("#intro")).toBeVisible();
    await expect(page.locator(".msg--visitor")).toHaveCount(0);

    await page.reload();
    await expect(page.locator("#intro")).toBeVisible();
    await expect(page.locator(".msg--visitor")).toHaveCount(0);
  });

  test("Keep chat off does not persist across reload", async ({ page }) => {
    await page.goto("/");
    await page.click("#keepChatToggle + .track"); // toggle the visible track; the input itself is pointer-events:none
    await page.fill("#messageInput", "Q5");
    await page.keyboard.press("Enter");
    await expect(page.locator(".msg--avatar").first()).toBeVisible({ timeout: 10_000 });

    await page.reload();
    await expect(page.locator("#intro")).toBeVisible();
    await expect(page.locator(".msg--visitor")).toHaveCount(0);
  });

  test("rate limit: 21st message in a minute is rejected with a friendly banner, no LLM call", async ({
    page,
  }) => {
    await page.goto("/");
    for (let i = 0; i < 20; i++) {
      await page.fill("#messageInput", "Q1");
      await page.keyboard.press("Enter");
      await expect(page.locator("#messageInput")).toBeEnabled({ timeout: 10_000 });
    }
    await page.fill("#messageInput", "Q1");
    await page.keyboard.press("Enter");
    await expect(page.locator(".banner")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".banner")).toContainText(/quickly|slow/i);
  });

  test("overlong message is truncated server-side with a note appended", async ({ page, request }) => {
    await page.goto("/");
    const conversationId = await page.evaluate(() => crypto.randomUUID());
    const longMessage = "a".repeat(20_050);
    const res = await request.post("/api/chat", {
      data: { conversation_id: conversationId, name: "Trunc Test", message: longMessage },
    });
    expect(res.ok()).toBeTruthy();
    const convo = await request.get(`/api/conversation/${conversationId}`);
    const body = await convo.json();
    const visitorRow = body.messages.find((m: { role: string }) => m.role === "visitor");
    expect(visitorRow.content.length).toBeLessThan(20_100);
    expect(visitorRow.content).toContain("[...message truncated");
  });
});

async function composerFocused(page: import("@playwright/test").Page): Promise<boolean> {
  return page.evaluate(() => document.activeElement?.id === "messageInput");
}
