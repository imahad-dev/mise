import { expect, test } from "@playwright/test";
import { ANGEETHI, KEHWA, NOOR, TIKKA, clearDemoLimits, openTable, openTableMenu, venueTables } from "./helpers";

// Phase 3: each venue's menu opens with a House favourites strip of its own 6-8 dish photos;
// a photo opens that dish's sheet with the same photo. The list below stays text-only.
test.beforeEach(() => clearDemoLimits());

for (const slug of [ANGEETHI, KEHWA, NOOR, TIKKA]) {
  test(`${slug}: House favourites strip and dish sheet photo`, async ({ page }) => {
    // A dine-in table, not the counter: counter menus are not opened through a sitting.
    const table = Object.values(await venueTables(slug)).find((t) => t.kind !== "counter")!;
    await openTable(slug, table.label);
    await openTableMenu(page, table.qr_token);

    const strip = page.locator("section", { has: page.getByRole("heading", { name: "House favourites" }) });
    const photos = strip.locator("img");
    const count = await photos.count();
    expect(count).toBeGreaterThanOrEqual(6);
    expect(count).toBeLessThanOrEqual(8);
    for (let i = 0; i < count; i++) {
      await photos.nth(i).scrollIntoViewIfNeeded();
      await expect(photos.nth(i)).toHaveAttribute("src", new RegExp(`^/venues/${slug}/dishes/[a-z0-9_]+\.webp$`));
      await expect.poll(() => photos.nth(i).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
    }

    // The strip's photos are the only images in the menu: the list below is text-only.
    await expect(page.locator("main li img")).toHaveCount(count);

    const src = await photos.first().getAttribute("src");
    await strip.getByRole("button").first().click();
    await expect(page.getByRole("dialog").locator(`img[src="${src}"]`)).toBeVisible();
  });
}
