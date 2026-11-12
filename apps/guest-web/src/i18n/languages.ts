/** The guest app's languages: English plus each venue's local language (spec 2026-11-09, phase 1b). */
export const GUEST_LANGUAGES = ["en", "ur", "ar"] as const;
export type GuestLanguage = (typeof GUEST_LANGUAGES)[number];

/** Each language in its own name and script, as the scan page shows it. */
export const LANGUAGE_NAMES: Record<GuestLanguage, string> = { en: "English", ur: "اردو", ar: "العربية" };

export const isGuestLanguage = (s: string): s is GuestLanguage => (GUEST_LANGUAGES as readonly string[]).includes(s);

export const isRtl = (lang: string) => lang === "ur" || lang === "ar";

/** The language a guest page should be in: the visit's, if the venue offers it, else the venue's default. */
export function languageFor(v: { languages: string[]; defaultLanguage: string; language?: string }): GuestLanguage {
  if (v.language && v.languages.includes(v.language) && isGuestLanguage(v.language)) return v.language;
  return isGuestLanguage(v.defaultLanguage) ? v.defaultLanguage : "en";
}
