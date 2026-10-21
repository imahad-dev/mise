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
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-danger-bg text-danger-fg border border-danger-fg/40 ${className}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-danger-fg animate-pulse" />
        {label}
      </span>
    );
  }

  if (status === "unverified") {
    return (
      <span
        data-testid="allergen-chip-unverified"
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-warn-bg text-warn-fg border border-warn-fg/30 ${className}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-warn-fg" />
        {dict.allergenStatus.unverified}
      </span>
    );
  }

  // "no_declared_match"
  return (
    <span
      data-testid="allergen-chip-no-declared-match"
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-safe-bg text-terracotta border border-terracotta ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-olive" />
      {dict.allergenStatus.no_declared_match}
    </span>
  );
}
