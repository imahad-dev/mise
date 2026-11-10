import type { CSSProperties } from "react";
import type { BrandTokens, VenueBrand } from "ui";

const SYSTEM = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";

/** The brand as CSS variables; globals.css maps them onto the theme. Ink and allergen colours stay fixed. */
export function brandStyle(t: BrandTokens, fonts?: Pick<VenueBrand, "displayFont" | "textFont">): CSSProperties {
  return {
    "--brand-deep": t.deep,
    "--brand-on-deep": t.onDeep,
    "--brand-surface": t.surface,
    "--brand-surface-2": t.surface2,
    "--brand-card": t.card,
    "--brand-line": t.line,
    "--brand-accent": t.accent,
    "--brand-accent-strong": t.accentStrong,
    "--brand-on-accent": t.onAccent,
    "--brand-spark": t.spark,
    "--brand-button-radius": t.buttonRadius,
    "--brand-card-radius": t.cardRadius,
    "--brand-display": fonts?.displayFont ?? SYSTEM,
    "--brand-text": fonts?.textFont ?? SYSTEM,
  } as CSSProperties;
}
