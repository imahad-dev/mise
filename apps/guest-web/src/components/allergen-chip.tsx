"use client";

import React from "react";
import { getDictionary } from "../i18n";

export interface AllergenChipProps {
  status: "contains" | "unverified" | "no_declared_match" | string;
  matchedAllergens?: string[];
  locale?: string;
  className?: string;
}

export function AllergenChip({
  status,
  matchedAllergens = [],
  locale = "en",
  className = "",
}: AllergenChipProps) {
  const dict = getDictionary(locale);

  if (status === "contains") {
    const allergenLabels = matchedAllergens.map(
      (a) => (dict.allergens as Record<string, string>)[a] || a
    );
    const label =
      allergenLabels.length > 0
        ? `${dict.allergenStatus.contains}: ${allergenLabels.join(", ")}`
        : dict.allergenStatus.contains;

    return (
      <span
        data-testid="allergen-chip-contains"
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-300 border border-rose-800/60 ${className}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-pulse" />
        {label}
      </span>
    );
  }

  if (status === "unverified") {
    return (
      <span
        data-testid="allergen-chip-unverified"
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-950/60 text-amber-300 border border-amber-800/50 ${className}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        {dict.allergenStatus.unverified}
      </span>
    );
  }

  // "no_declared_match"
  return (
    <span
      data-testid="allergen-chip-no-declared-match"
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/50 ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
      {dict.allergenStatus.no_declared_match}
    </span>
  );
}
