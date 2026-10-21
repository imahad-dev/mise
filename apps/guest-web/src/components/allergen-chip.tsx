"use client";

import React from "react";
import { StatusChip } from "ui";
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
    const names = matchedAllergens.map((a) => (dict.allergens as Record<string, string>)[a] || a);
    const label = names.length
      ? `${dict.allergenStatus.contains}: ${names.join(", ")}`
      : dict.allergenStatus.contains;
    return (
      <StatusChip tone="contains" data-testid="allergen-chip-contains" className={className}>
        {label}
      </StatusChip>
    );
  }

  if (status === "unverified") {
    return (
      <StatusChip tone="unverified" data-testid="allergen-chip-unverified" className={className}>
        {dict.allergenStatus.unverified}
      </StatusChip>
    );
  }

  return (
    <StatusChip tone="safe" data-testid="allergen-chip-no-declared-match" className={className}>
      {dict.allergenStatus.no_declared_match}
    </StatusChip>
  );
}
