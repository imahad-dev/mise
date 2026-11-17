import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Dish photos (spec 2026-11-09, phase 3): every photo has a free-licence credit, every credit
// and every seed image_url points at a real file, and nothing is left unused.
const ROOT = fileURLToPath(new URL("../../../../", import.meta.url));
const PUBLIC = join(ROOT, "apps/guest-web/public");
const LICENCES = ["Unsplash License", "Pexels License", "CC0 1.0"];
const MAX_BYTES = 200 * 1024;

interface Credit {
  dish: string;
  source_url: string;
  author: string;
  licence: string;
}
const credits: Record<string, Credit> = JSON.parse(
  readFileSync(join(ROOT, "data/photo_credits.json"), "utf8"),
);

const photos = readdirSync(join(PUBLIC, "venues")).flatMap((slug) => {
  const dir = join(PUBLIC, "venues", slug, "dishes");
  return existsSync(dir) ? readdirSync(dir).map((f) => `/venues/${slug}/dishes/${f}`) : [];
});

const seedUrls: string[] = readdirSync(join(ROOT, "data/seed"))
  .filter((f) => f.endsWith(".json"))
  .flatMap((f) => JSON.parse(readFileSync(join(ROOT, "data/seed", f), "utf8")).items ?? [])
  .map((i: { image_url?: string | null }) => i.image_url)
  .filter((u: string | null | undefined): u is string => Boolean(u));

describe("dish photos", () => {
  it.each(photos)("%s is a small WebP with a free-licence credit", (photo) => {
    expect(photo).toMatch(/^\/venues\/[a-z-]+\/dishes\/[a-z0-9_]+\.webp$/);
    expect(statSync(join(PUBLIC, photo)).size).toBeLessThanOrEqual(MAX_BYTES);
    const c = credits[photo];
    expect(c, `no credit for ${photo}`).toBeDefined();
    expect(c.source_url).toMatch(/^https:\/\//);
    expect(c.author.trim()).not.toBe("");
    expect(c.dish.trim()).not.toBe("");
    expect(LICENCES).toContain(c.licence);
  });

  it("every credit names a photo that exists", () => {
    expect(Object.keys(credits).filter((p) => !photos.includes(p))).toEqual([]);
  });

  it("every seed image_url is a photo that exists, and every photo is used", () => {
    expect(seedUrls.filter((u) => !photos.includes(u))).toEqual([]);
    expect(photos.filter((p) => !seedUrls.includes(p))).toEqual([]);
  });
});
