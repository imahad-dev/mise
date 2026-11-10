import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { VENUE_BRANDS } from "ui";

const repo = path.resolve(process.cwd(), "../..");
const SOURCE: Record<string, string> = { "angeethi-house": "angeethi", "kehwa-and-crumb": "kehwa" };

describe.each(Object.keys(VENUE_BRANDS))("%s logo files", (slug) => {
  it.each(["mark", "lockup"])("%s.svg is the round-1 vector in both apps", (kind) => {
    const original = readFileSync(path.join(repo, "docs/brand/round-1", `${SOURCE[slug]}-${kind}.svg`));
    for (const app of ["guest-web", "owner-web"]) {
      const copy = readFileSync(path.join(repo, "apps", app, "public/venues", slug, `${kind}.svg`));
      expect(copy.equals(original), `${app} ${slug}/${kind}.svg`).toBe(true);
      expect(copy.toString()).toMatch(/^<svg[\s\S]*<\/svg>\s*$/);
      expect(copy.toString()).not.toMatch(/<image|data:image/);
    }
  });
});
