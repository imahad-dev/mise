import { describe, it, expect } from "vitest";
import { translate, getDictionary, en, it as itDict } from "./index";

describe("i18n dictionary and fallback mechanism", () => {
  it("returns English strings for English locale", () => {
    const dict = getDictionary("en");
    expect(dict.staffNotice).toBe(en.staffNotice);
    expect(dict.ui.menuTitle).toBe("Menu");
    expect(dict.allergenStatus.contains).toBe("Contains");
    expect(dict.allergens.gluten).toBe("Gluten");
  });

  it("returns Italian strings for Italian locale", () => {
    const dict = getDictionary("it");
    expect(dict.staffNotice).toBe(itDict.staffNotice);
    expect(dict.ui.menuTitle).toBe("Menu");
    expect(dict.allergenStatus.contains).toBe("Contiene");
    expect(dict.allergens.gluten).toBe("Glutine");
  });

  it("falls back to English when an unsupported or unknown locale is requested", () => {
    const dict = getDictionary("fr");
    expect(dict.staffNotice).toBe(en.staffNotice);
    expect(dict.allergenStatus.unverified).toBe(en.allergenStatus.unverified);
    expect(dict.allergens.peanuts).toBe("Peanuts");
  });

  it("falls back to English for missing nested keys using translate()", () => {
    // Standard keys in it
    expect(translate("it", "allergenStatus.contains")).toBe("Contiene");

    // Existing key in en
    expect(translate("en", "ui.orderStatus")).toBe("Order Status");

    // Missing key in it falls back to English
    expect(translate("it", "nonexistent.key")).toBe("nonexistent.key");
    expect(translate("unknown-locale", "ui.welcomeTitle")).toBe(en.ui.welcomeTitle);
  });

  it("includes the mandatory 'please confirm with staff' notice in both dictionaries", () => {
    expect(en.staffNotice).toContain("confirm all allergen risks with staff");
    expect(itDict.staffNotice).toContain("con il personale");
  });
});
