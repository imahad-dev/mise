import { expect, test } from "@playwright/test";
import { GUEST, demoInfo, skipWelcome } from "./helpers";

// A guest sees only the venue they scanned: no other venue, no venue list, no Mise.
test.describe("one venue per guest", () => {
  test("no other venue and no Mise anywhere a guest can go", async ({ browser, request }) => {
    const { venues } = await demoInfo();
    expect(venues.length).toBeGreaterThanOrEqual(2);

    for (const venue of venues) {
      const forbidden = [...venues.filter((o) => o.slug !== venue.slug).map((o) => o.name), "Mise"];
      const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
      const page = await context.newPage();

      const check = async (where: string, expectName: boolean) => {
        const text = await page.locator("body").innerText();
        const title = await page.title();
        const images = await page.$$eval("img", (els) =>
          els.map((e) => `${e.getAttribute("src")} ${e.getAttribute("alt")}`).join(" "),
        );
        const icons = await page.$$eval("link[rel~='icon'], link[rel='apple-touch-icon']", (els) =>
          els.map((e) => e.getAttribute("href")).join(" "),
        );
        const manifestHref = await page.locator("link[rel='manifest']").getAttribute("href", { timeout: 1000 }).catch(() => null);
        const manifest = manifestHref ? await (await request.get(new URL(manifestHref, GUEST).href)).text() : "";
        for (const word of forbidden) {
          for (const [label, value] of Object.entries({ text, title, images, icons, manifest })) {
            expect(value, `${venue.name} · ${where} · ${label} names "${word}"`).not.toContain(word);
          }
        }
        expect(await page.locator('a[href="/"]').count(), `${where} links to the venue list`).toBe(0);
        expect(icons, `${where} uses the Mise icon`).not.toContain("/brand/logo-mark");
        if (expectName) expect(title, `${where} title`).toContain(venue.name);
      };

      await page.goto(`${GUEST}/q/${venue.qr_token}`);
      await check("scan page", true);

      await page.getByRole("button", { name: "View Menu" }).click();
      await expect(page).toHaveURL(/\/en\/menu$/);
      await skipWelcome(page);
      await check("menu", true);

      await page.getByRole("button", { name: `Ask ${venue.name}` }).click();
      await check("menu with the assistant open", true);
      await page.getByRole("button", { name: "Close", exact: true }).click();

      await page.locator("main li").first().click(); // opens the dish sheet
      await check("dish sheet", true);
      await page.keyboard.press("Escape");

      await page.goto(`${GUEST}/en/orders/00000000-0000-0000-0000-000000000000`);
      await check("unknown order", true);

      await page.goto(`${GUEST}/no-such-page`);
      await check("not-found page", false);

      await page.goto(`${GUEST}/q/not-a-real-token`);
      await check("bad QR code", false);
      await expect(page.getByText("Scan the QR code on your table again.")).toBeVisible();

      await context.clearCookies();
      await page.goto(`${GUEST}/en/menu`);
      await check("expired visit", false);
      await expect(page.getByText("Scan the QR code on your table again.")).toBeVisible();

      await context.close();
    }
  });

  test("the welcome plays once per visit, can be tapped away and never blocks for more than 3 s", async ({ browser }) => {
    const { venues } = await demoInfo();
    const venue = venues[0];

    const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const page = await context.newPage();
    await page.goto(`${GUEST}/q/${venue.qr_token}`);
    await page.getByRole("button", { name: "View Menu" }).click();
    await expect(page).toHaveURL(/\/en\/menu$/);
    const welcome = page.getByTestId("welcome");
    await expect(welcome).toBeVisible({ timeout: 10_000 });
    const shownAt = Date.now();
    await expect(welcome).toBeHidden({ timeout: 3_500 }); // closes by itself
    expect(Date.now() - shownAt).toBeLessThan(3_500);

    await page.reload(); // same visit: not again
    await expect(page.locator("[data-welcome]").first()).toHaveAttribute("data-welcome", "done", { timeout: 10_000 });
    await expect(welcome).toHaveCount(0);
    await context.close();

    // Smallest phone, reduced motion: a tap skips it at once and the menu underneath is ready.
    const small = await browser.newContext({ viewport: { width: 320, height: 568 }, reducedMotion: "reduce" });
    const p2 = await small.newPage();
    await p2.goto(`${GUEST}/q/${venue.qr_token}`);
    await p2.getByRole("button", { name: "View Menu" }).click();
    const w2 = p2.getByTestId("welcome");
    await expect(w2).toBeVisible({ timeout: 10_000 });
    await w2.click();
    await expect(w2).toBeHidden();
    await expect(p2.locator("main li").first()).toBeVisible();
    await small.close();
  });
});
