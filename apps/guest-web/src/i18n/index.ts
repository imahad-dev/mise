import { en } from "./en";
import { it } from "./it";
import type { TranslationDict } from "./types";

export * from "./types";
export { en, it };

const dictionaries: Record<string, Partial<TranslationDict>> = {
  en,
  it,
};

/**
 * Retrieve a nested translation string with automatic fallback to English.
 * Supports dot-notated paths, e.g. "ui.welcomeTitle" or "allergens.gluten" or "staffNotice".
 */
export function translate(locale: string | undefined | null, keyPath: string): string {
  const targetLocale = (locale || "en").toLowerCase();
  const dict = dictionaries[targetLocale] || en;

  const value = getNestedValue(dict, keyPath);
  if (typeof value === "string" && value.length > 0) {
    return value;
  }

  // Fallback to English dictionary
  const fallbackValue = getNestedValue(en, keyPath);
  if (typeof fallbackValue === "string") {
    return fallbackValue;
  }

  return keyPath;
}

function getNestedValue(obj: unknown, path: string): unknown {
  if (!obj || typeof obj !== "object") return undefined;
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === "object" && part in current) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

/**
 * Returns a complete TranslationDict for the given locale with deep English fallback for any missing key.
 */
export function getDictionary(locale: string | undefined | null): TranslationDict {
  const targetLocale = (locale || "en").toLowerCase();
  const raw = dictionaries[targetLocale];
  if (!raw || targetLocale === "en") {
    return en;
  }

  return {
    staffNotice: raw.staffNotice || en.staffNotice,
    allergens: {
      ...en.allergens,
      ...(raw.allergens || {}),
    },
    dietary: {
      ...en.dietary,
      ...(raw.dietary || {}),
    },
    allergenStatus: {
      ...en.allergenStatus,
      ...(raw.allergenStatus || {}),
    },
    ui: {
      ...en.ui,
      ...(raw.ui || {}),
    },
  };
}
