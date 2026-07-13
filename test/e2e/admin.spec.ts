import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { loadRootEnv } from "./helpers";

const ADMIN_PASSWORD = loadRootEnv().ADMIN_PASSWORD!;

async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto("/admin");
  await page.fill("#passwordInput", ADMIN_PASSWORD);
  await page.click('#loginForm button[type="submit"]');
  await expect(page.locator("#dashboard")).toBeVisible();
}

async function seedContactCaptureConversation(request: APIRequestContext): Promise<string> {
  const conversationId = crypto.randomUUID();
  await request.post("/api/chat", {
    data: {
      conversation_id: conversationId,
      name: "Attn Test",
      message: "I'd like to get in touch, how do I reach the human directly?",
    },
  });
  await request.post("/api/chat", {
    data: {
      conversation_id: conversationId,
      name: "Attn Test",
      message: "Sure, my email is attn-test@example.com",
    },
  });
  return conversationId;
}

test.describe("Admin dashboard", () => {
  test("login gate: wrong password rejected, correct password enters", async ({ page }, testInfo) => {
    await page.goto("/admin");
    await expect(page.locator("#loginGate")).toBeVisible();
    await expect(page.locator("#passwordInput")).toBeFocused();

    await page.fill("#passwordInput", "definitely-wrong-password");
    await page.click('#loginForm button[type="submit"]');
    await expect(page.locator("#loginError")).toBeVisible();
    await page.screenshot({ path: `screenshots/admin/01-login-error-${testInfo.project.name}.png` });

    await page.fill("#passwordInput", ADMIN_PASSWORD);
    await page.click('#loginForm button[type="submit"]');
    await expect(page.locator("#dashboard")).toBeVisible();
    await expect(page.locator("#loginGate")).toBeHidden();
    await page.screenshot({
      path: `screenshots/admin/02-dashboard-${testInfo.project.name}.png`,
      fullPage: true,
    });
  });

  test("dark/light theme on dashboard", async ({ page }, testInfo) => {
    await loginAsAdmin(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({ path: `screenshots/admin/03-dark-${testInfo.project.name}.png`, fullPage: true });
    await page.click("#themeToggle");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.screenshot({ path: `screenshots/admin/04-light-${testInfo.project.name}.png`, fullPage: true });
  });

  test("needs_attention flag shows in inbox, clears on open", async ({ page, request }, testInfo) => {
    const conversationId = await seedContactCaptureConversation(request);
    await loginAsAdmin(page);
    await page.reload();

    const row = page.locator(`.convo-item[data-id="${conversationId}"]`);
    await expect(row).toHaveClass(/is-attention/, { timeout: 15_000 });
    await page.screenshot({ path: `screenshots/admin/05-inbox-attention-${testInfo.project.name}.png` });

    await row.click();
    await expect(page.locator("#threadView")).toBeVisible();
    await expect(page.locator(".msg--avatar").first()).toBeVisible();
    await page.screenshot({
      path: `screenshots/admin/06-thread-open-${testInfo.project.name}.png`,
      fullPage: true,
    });

    await expect(row).not.toHaveClass(/is-attention/);
  });

  test("admin reply appears to the visitor as the live human bubble via polling", async ({ browser }, testInfo) => {
    const visitorContext = await browser.newContext();
    const visitorPage = await visitorContext.newPage();
    await visitorPage.goto("/");
    await visitorPage.fill("#nameInput", "Poll Test");
    await visitorPage.fill("#messageInput", "Q1");
    await visitorPage.keyboard.press("Enter");
    await expect(visitorPage.locator(".msg--avatar").first()).toBeVisible({ timeout: 10_000 });

    const conversationId = await visitorPage.evaluate(
      () => document.cookie.match(/avatar_conversation_id=([^;]+)/)?.[1] ?? "",
    );
    expect(conversationId).toBeTruthy();

    const adminContext = await browser.newContext();
    const adminPage = await adminContext.newPage();
    await loginAsAdmin(adminPage);
    await adminPage.reload();
    await adminPage.locator(`.convo-item[data-id="${conversationId}"]`).click();
    await expect(adminPage.locator("#threadView")).toBeVisible();
    await adminPage.fill("#adminMessageInput", "This is the human, jumping in.");
    await adminPage.keyboard.press("Enter");
    await expect(adminPage.locator(".msg--human").first()).toBeVisible();
    await adminPage.screenshot({
      path: `screenshots/admin/07-human-reply-sent-${testInfo.project.name}.png`,
      fullPage: true,
    });

    // visitor picks it up via polling (fast cadence is 10s)
    await expect(visitorPage.locator(".msg--human").first()).toBeVisible({ timeout: 15_000 });
    await expect(visitorPage.locator(".msg--human .human-tag")).toContainText("live");
    await visitorPage.screenshot({
      path: `screenshots/visitor/06-human-bubble-${testInfo.project.name}.png`,
      fullPage: true,
    });

    await visitorContext.close();
    await adminContext.close();
  });

  test("mobile master/detail: back control returns to inbox", async ({ page, request }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("mobile"), "master/detail is mobile-only behavior");
    // seeding does 2 sequential real LLM turns (2nd fires push_tool + a live Pushover call) -- give it room.
    test.setTimeout(90_000);
    await seedContactCaptureConversation(request);
    await loginAsAdmin(page);
    await page.reload();
    await page.locator(".convo-item").first().click();
    await expect(page.locator("body")).toHaveClass(/detail-open/);
    await expect(page.locator("#threadView")).toBeVisible();
    // #threadView becomes visible synchronously, before the async fetch that actually
    // populates it -- wait for real content, not just the shell, before asserting/screenshotting.
    await expect(page.locator(".msg").first()).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: `screenshots/admin/08-mobile-detail-${testInfo.project.name}.png`, fullPage: true });

    await page.click("#backBtn");
    await expect(page.locator("body")).not.toHaveClass(/detail-open/);
    await page.screenshot({ path: `screenshots/admin/09-mobile-inbox-${testInfo.project.name}.png`, fullPage: true });
  });

  test("keyboard arrow navigation moves selection between conversations", async ({ page, request }) => {
    await seedContactCaptureConversation(request);
    await seedContactCaptureConversation(request);
    await loginAsAdmin(page);
    await page.reload();

    await page.locator(".convo-item").first().click();
    const firstId = await page.locator(".convo-item.is-active").getAttribute("data-id");
    await page.keyboard.press("ArrowDown");
    const secondId = await page.locator(".convo-item.is-active").getAttribute("data-id");
    expect(secondId).not.toBe(firstId);
  });

  test("mark resolved clears the attention flag without replying", async ({ page, request }) => {
    const conversationId = await seedContactCaptureConversation(request);
    await loginAsAdmin(page);
    await page.reload();
    const row = page.locator(`.convo-item[data-id="${conversationId}"]`);
    await expect(row).toHaveClass(/is-attention/, { timeout: 15_000 });
    await row.click();

    // re-trigger attention without reopening, to prove "Mark resolved" (not just "open") clears it
    await request.post(`/admin/conversations/${conversationId}/messages`, {
      data: { content: "placeholder" },
    });

    await page.click("#resolveBtn");
    await expect(page.locator("#attnFlag")).toBeHidden();
    await expect(row).not.toHaveClass(/is-attention/);
  });

  test("poll does not silently re-clear needs_attention on the already-open thread", async ({ page, request }) => {
    // RECS.md: "Admin's own poll re-clears needs_attention before the human
    // notices". Open the thread (clears the flag, as expected for a deliberate
    // click), re-trigger it while still open (a real 2nd contact-capture flow on
    // the same conversation), then wait past a poll tick (10s) and confirm the
    // flag survives instead of the poll silently clearing it again.
    test.setTimeout(60_000);
    const conversationId = await seedContactCaptureConversation(request);
    await loginAsAdmin(page);
    await page.reload();
    const row = page.locator(`.convo-item[data-id="${conversationId}"]`);
    await expect(row).toHaveClass(/is-attention/, { timeout: 15_000 });

    await row.click();
    await expect(page.locator("#threadView")).toBeVisible();
    await expect(row).not.toHaveClass(/is-attention/); // the deliberate open cleared it

    await request.post("/api/chat", {
      data: { conversation_id: conversationId, message: "Actually, can you connect me with the human again?" },
    });
    await request.post("/api/chat", {
      data: { conversation_id: conversationId, message: "My email is retest-poll@example.com" },
    });
    await expect(row).toHaveClass(/is-attention/, { timeout: 15_000 });
    await expect(page.locator("#attnFlag")).toBeVisible();

    // Past a poll tick (POLL_MS = 10s): without the fix, pollTick() re-fetches the
    // open thread via the mutating admin endpoint and silently clears this again.
    await page.waitForTimeout(12_000);
    await expect(row).toHaveClass(/is-attention/);
    await expect(page.locator("#attnFlag")).toBeVisible();
  });

  test("switching threads mid-fetch does not leak the stale thread's rows into the new one", async ({
    page,
    request,
  }) => {
    // RECS.md: "Rapid UI actions (... switch admin threads mid-reply) can render
    // into the wrong panel". Delay conversation A's fetch, switch to B before A
    // resolves, then let A's (now-stale) response through and confirm it never
    // gets applied on top of B.
    const idA = await seedContactCaptureConversation(request);
    const idB = crypto.randomUUID();
    await request.post("/api/chat", { data: { conversation_id: idB, message: "Q1" } });

    await loginAsAdmin(page);
    await page.reload();

    let releaseA: () => void;
    const gateA = new Promise<void>((resolve) => {
      releaseA = resolve;
    });
    await page.route(`**/admin/conversations/${idA}`, async (route) => {
      await gateA;
      await route.continue();
    });

    await page.locator(`.convo-item[data-id="${idA}"]`).click(); // starts A's (gated) fetch
    await page.locator(`.convo-item[data-id="${idB}"]`).click(); // switches to B first
    await expect(page.locator(".msg").first()).toBeVisible({ timeout: 10_000 });
    const countAfterB = await page.locator(".msg").count();

    releaseA!(); // let A's delayed response arrive now, after B is already active
    await page.waitForTimeout(1000);

    await expect(page.locator(".msg")).toHaveCount(countAfterB);
  });

  test("inbox shows a banner when the scan was truncated (there may be more)", async ({ page }) => {
    // RECS.md: "Admin inbox silently caps at a 3000-row scan window, no 'there
    // may be more' UI signal". Mocked response, since seeding 3000+ real rows
    // just to trigger this is impractical.
    await loginAsAdmin(page);
    await page.route("**/admin/conversations", (route) =>
      route.request().method() === "GET"
        ? route.fulfill({ json: { conversations: [], scan_truncated: true } })
        : route.continue(),
    );
    await page.reload();
    await expect(page.locator("#scanTruncatedBanner")).toBeVisible();

    await page.unroute("**/admin/conversations");
    await page.route("**/admin/conversations", (route) =>
      route.request().method() === "GET"
        ? route.fulfill({ json: { conversations: [], scan_truncated: false } })
        : route.continue(),
    );
    await page.reload();
    await expect(page.locator("#scanTruncatedBanner")).toBeHidden();
  });

  test("logout returns to the login gate", async ({ page }) => {
    await loginAsAdmin(page);
    await page.click("#logoutBtn");
    await expect(page.locator("#loginGate")).toBeVisible();
  });
});
