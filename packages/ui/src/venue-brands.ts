/** Static brand data per venue: colours, names and font stacks. Shared by the guest app (every
 *  guest screen) and the owner app (QR cards and the sample bill). Venue code (fonts, motif,
 *  animations) lives in apps/guest-web/src/brands/<slug>/. */

export interface BrandTokens {
  /** Masthead band, behind the light logo lockup. */
  deep: string;
  /** Logo and text on `deep`. */
  onDeep: string;
  surface: string;
  surface2: string;
  card: string;
  /** Hairlines; any CSS colour (not contrast-checked). */
  line: string;
  accent: string;
  accentStrong: string;
  onAccent: string;
  /** Decoration only (motif, animation), never text. */
  spark: string;
  buttonRadius: string;
  cardRadius: string;
  /** Weight of h1-h3 on the guest pages; null keeps the weights each heading sets itself. */
  headingWeight: string | null;
}

export interface VenueBrand {
  slug: string;
  /** Must equal the venue's name in data/seed. */
  name: string;
  tokens: BrandTokens;
  /** CSS font stacks; the first entry is the venue face loaded with next/font. */
  displayFont: string;
  textFont: string;
}

export const NEUTRAL_TOKENS: BrandTokens = {
  deep: "#2f2f2f",
  onDeep: "#ffffff",
  surface: "#f7f7f5",
  surface2: "#ededea",
  card: "#ffffff",
  line: "rgb(0 0 0 / 0.12)",
  accent: "#2f2f2f",
  accentStrong: "#1a1a1a",
  onAccent: "#ffffff",
  spark: "#9a9a9a",
  buttonRadius: "10px",
  cardRadius: "12px",
  headingWeight: null,
};

export const VENUE_BRANDS: Record<string, VenueBrand> = {
  "angeethi-house": {
    slug: "angeethi-house",
    name: "Angeethi House",
    tokens: {
      deep: "#7f011f",
      onDeep: "#f5ebdd",
      surface: "#f5ebdd",
      surface2: "#ebdcc8",
      card: "#fbf6ee",
      line: "rgb(127 1 31 / 0.16)",
      accent: "#7f011f",
      accentStrong: "#5e0016",
      onAccent: "#f5ebdd",
      spark: "#ff9a3d",
      buttonRadius: "4px",
      cardRadius: "6px",
      headingWeight: null,
    },
    displayFont: "var(--brand-display-face, Impact), Impact, 'Arial Narrow', sans-serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
  "kehwa-and-crumb": {
    slug: "kehwa-and-crumb",
    name: "Kehwa & Crumb",
    tokens: {
      deep: "#064734",
      onDeep: "#e0ffc2",
      surface: "#f3f8ea",
      surface2: "#e4efd3",
      card: "#fafdf5",
      line: "rgb(6 71 52 / 0.15)",
      accent: "#064734",
      accentStrong: "#04331f",
      onAccent: "#e0ffc2",
      spark: "#b8e68c",
      buttonRadius: "9999px",
      cardRadius: "20px",
      headingWeight: "300",
    },
    displayFont: "var(--brand-display-face, 'Futura'), 'Futura', 'Century Gothic', sans-serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
  "noor-and-zaatar": {
    slug: "noor-and-zaatar",
    name: "Noor & Za'atar",
    tokens: {
      deep: "#014BAA",
      onDeep: "#F8F3F0",
      surface: "#F8F3F0",
      surface2: "#ECE4DA",
      card: "#FFFCF8",
      line: "rgb(1 75 170 / 0.15)",
      accent: "#014BAA",
      accentStrong: "#013A85",
      onAccent: "#F8F3F0",
      spark: "#E9A93B",
      // Arches from the logo: round top, nearly square base.
      buttonRadius: "999px 999px 10px 10px",
      cardRadius: "28px 28px 10px 10px",
      headingWeight: "600",
    },
    displayFont: "var(--brand-display-face, Georgia), Georgia, serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
  "tikka-town": {
    slug: "tikka-town",
    name: "Tikka Town",
    tokens: {
      deep: "#9E2B12",
      onDeep: "#FDFDF1",
      surface: "#FDFDF1",
      surface2: "#F6EBD7",
      card: "#FFFFFA",
      line: "rgb(158 43 18 / 0.18)",
      accent: "#9E2B12",
      accentStrong: "#7A200C",
      onAccent: "#FDFDF1",
      spark: "#E8B23A",
      buttonRadius: "2px",
      cardRadius: "2px",
      // Bebas Neue has one weight; a bold heading would be faked and smeared.
      headingWeight: "400",
    },
    displayFont: "var(--brand-display-face, Impact), Impact, 'Arial Narrow', sans-serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
};

export function venueBrand(slug: string | null | undefined): VenueBrand | null {
  if (!slug || !Object.prototype.hasOwnProperty.call(VENUE_BRANDS, slug)) return null;
  return VENUE_BRANDS[slug];
}

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a hex colour: ${hex}`);
  const h = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2 contrast ratio between two hex colours (1 to 21). */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
