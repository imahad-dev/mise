import { describe, expect, it } from "vitest";
import { GUEST_LANGUAGES, LANGUAGE_NAMES, isGuestLanguage, isRtl, languageFor } from "./languages";

describe("guest languages", () => {
  it("knows exactly en, ur and ar", () => {
    expect([...GUEST_LANGUAGES]).toEqual(["en", "ur", "ar"]);
    for (const bad of ["it", "EN", "ur-PK", "", "..", "en/../ar"]) expect(isGuestLanguage(bad)).toBe(false);
  });

  it("names each language in its own script", () => {
    expect(LANGUAGE_NAMES).toEqual({ en: "English", ur: "اردو", ar: "العربية" });
  });

  it("only Urdu and Arabic are right-to-left", () => {
    expect([isRtl("en"), isRtl("ur"), isRtl("ar")]).toEqual([false, true, true]);
  });

  it("the page follows the visit's language when the venue offers it", () => {
    const venue = { languages: ["en", "ur"], defaultLanguage: "en" };
    expect(languageFor({ ...venue, language: "ur" })).toBe("ur");
    expect(languageFor({ ...venue, language: "en" })).toBe("en");
  });

  it("a visit language the venue does not offer falls back to the venue default", () => {
    expect(languageFor({ languages: ["en", "ur"], defaultLanguage: "en", language: "it" })).toBe("en");
    expect(languageFor({ languages: ["en"], defaultLanguage: "en", language: "ar" })).toBe("en");
    expect(languageFor({ languages: ["en", "ur"], defaultLanguage: "en", language: undefined })).toBe("en");
  });

  it("a broken default never yields a language outside the known three", () => {
    expect(languageFor({ languages: [], defaultLanguage: "it", language: "it" })).toBe("en");
  });
});
