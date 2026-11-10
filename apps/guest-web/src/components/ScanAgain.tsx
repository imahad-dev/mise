import React from "react";
import { NEUTRAL_TOKENS } from "ui";
import { brandStyle } from "../brands/style";
import { getDictionary } from "../i18n";

/** Shown for a bad QR code, an expired visit or a missing page: no venue, no Mise, no links. */
export function ScanAgain({ lang }: { lang: string }) {
  const dict = getDictionary(lang);
  return (
    <main
      data-brand="neutral"
      style={brandStyle(NEUTRAL_TOKENS)}
      className="flex min-h-screen items-center justify-center bg-paper px-6 text-center text-ink"
    >
      <p className="max-w-xs text-lg font-semibold">{dict.ui.scanAgain}</p>
    </main>
  );
}
