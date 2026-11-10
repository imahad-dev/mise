import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { VENUE_BRANDS } from "ui";
import { BRAND_SLUGS, loadBrand } from "./index";

describe("brand registry", () => {
  it("returns null for an unknown or hostile slug", async () => {
    for (const bad of ["", "nope", "__proto__", "constructor", "../angeethi-house"]) {
      await expect(loadBrand(bad)).resolves.toBeNull();
    }
  });
  it("has a package for every venue brand and nothing more", () => {
    expect([...BRAND_SLUGS].sort()).toEqual(Object.keys(VENUE_BRANDS).sort());
  });
  it("no brand package imports another brand", () => {
    const dir = path.join(process.cwd(), "src/brands");
    for (const slug of BRAND_SLUGS) {
      for (const file of readdirSync(path.join(dir, slug))) {
        const src = readFileSync(path.join(dir, slug, file), "utf8");
        for (const other of BRAND_SLUGS.filter((s) => s !== slug)) expect(src, `${slug}/${file}`).not.toContain(other);
      }
    }
  });
});
