import type { BrandPackage } from "./types";

// Each venue's package is its own chunk: fonts, motif and GSAP load only on that venue's pages.
const PACKAGES: Record<string, () => Promise<BrandPackage>> = {
  "angeethi-house": () => import("./angeethi-house").then((m) => m.brand),
  "kehwa-and-crumb": () => import("./kehwa-and-crumb").then((m) => m.brand),
  "noor-and-zaatar": () => import("./noor-and-zaatar").then((m) => m.brand),
  "tikka-town": () => import("./tikka-town").then((m) => m.brand),
};

export const BRAND_SLUGS = Object.keys(PACKAGES);

export async function loadBrand(slug: string): Promise<BrandPackage | null> {
  if (!Object.prototype.hasOwnProperty.call(PACKAGES, slug)) return null;
  return PACKAGES[slug]();
}
