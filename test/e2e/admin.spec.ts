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

  test("mobile master/detail: back control returns to inbox", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "master/detail is mobile-only behavior");
    await loginAsAdmin(page);
    await page.reload();
    await page.locator(".convo-item").first().click();
    await expect(page.locator("body")).toHaveClass(/detail-open/);
    await expect(page.locator("#threadView")).toBeVisible();
    await page.screenshot({ path: "screenshots/admin/08-mobile-detail.png", fullPage: true });

    await page.click("#backBtn");
    await expect(page.locator("body")).not.toHaveClass(/detail-open/);
    await page.screenshot({ path: "screenshots/admin/09-mobile-inbox.png", fullPage: true });
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

  test("logout returns to the login gate", async ({ page }) => {
    await loginAsAdmin(page);
    await page.click("#logoutBtn");
    await expect(page.locator("#loginGate")).toBeVisible();
  });
});
