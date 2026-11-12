import { describe, it, expect } from "vitest";
import { translate, getDictionary, withVenue } from "./index";
import { en } from "./en";
import { ur } from "./ur";

function leaves(obj: unknown, prefix = ""): [string, string][] {
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    typeof v === "string" ? [[`${prefix}${k}`, v] as [string, string]] : leaves(v, `${prefix}${k}.`),
  );
}

describe("i18n dictionary and fallback mechanism", () => {
  it("returns English strings for English locale", () => {
    const dict = getDictionary("en");
    expect(dict.staffNotice).toBe(en.staffNotice);
    expect(dict.ui.menuTitle).toBe("Menu");
    expect(dict.allergenStatus.contains).toBe("Contains");
    expect(dict.allergens.gluten).toBe("Gluten");
  });

  it("falls back to English when an unsupported or unknown locale is requested", () => {
    const dict = getDictionary("fr");
    expect(dict.staffNotice).toBe(en.staffNotice);
    expect(dict.allergenStatus.unverified).toBe(en.allergenStatus.unverified);
    expect(dict.allergens.peanuts).toBe("Peanuts");
  });

  it("falls back to English for missing nested keys using translate()", () => {
    expect(translate("ur", "allergenStatus.contains")).toBe(ur.allergenStatus.contains);
    expect(translate("en", "ui.orderStatus")).toBe("Order Status");
    expect(translate("ur", "nonexistent.key")).toBe("nonexistent.key");
    expect(translate("unknown-locale", "ui.welcomeTitle")).toBe(en.ui.welcomeTitle);
  });

  it("includes the mandatory 'please confirm with staff' notice", () => {
    expect(en.staffNotice).toContain("confirm all allergen risks with staff");
  });
});

describe("Urdu dictionary", () => {
  const enLeaves = new Map(leaves(en));
  const urLeaves = new Map(leaves(ur));

  it("has every English key and nothing extra", () => {
    expect([...urLeaves.keys()].sort()).toEqual([...enLeaves.keys()].sort());
  });

  it("has no empty value and never names the platform", () => {
    for (const [key, value] of urLeaves) {
      expect(value.trim(), key).not.toBe("");
      expect(value, key).not.toMatch(/mise/i);
    }
  });

  it("keeps every placeholder of the English text", () => {
    for (const [key, value] of enLeaves) {
      const holes = value.match(/\{\w+\}/g) ?? [];
      for (const hole of holes) expect(urLeaves.get(key), `${key} ${hole}`).toContain(hole);
    }
  });

  it("is written in Urdu script, apart from brand and method names", () => {
    const latinOnly = new Set(["pay.methods.wallet", "pay.methods.raast", "pay.labels.raast_id", "pay.labels.jazzcash", "pay.labels.easypaisa", "pay.labels.iban"]);
    for (const [key, value] of urLeaves) {
      if (!latinOnly.has(key)) expect(value, key).toMatch(/[؀-ۿ]/);
    }
  });

  it("serves Urdu for ur and English for an unknown locale", () => {
    expect(getDictionary("ur").allergenStatus.contains).toBe(ur.allergenStatus.contains);
    expect(getDictionary("it")).toBe(en);
    expect(translate("it", "allergenStatus.contains")).toBe("Contains");
  });
});

describe("venue-named strings", () => {
  it("puts the venue name into the titles in both languages", () => {
    expect(withVenue(en.ui.welcomeTitle, "Angeethi House")).toBe("Welcome to Angeethi House");
    expect(withVenue(en.ui.chatTitle, "Kehwa & Crumb")).toBe("Ask Kehwa & Crumb");
    expect(withVenue(ur.ui.welcomeTitle, "Angeethi House")).toBe(ur.ui.welcomeTitle.replace("{venue}", "Angeethi House"));
  });
  it("treats special characters in a name as plain text", () => {
    expect(withVenue("Ask {venue}", "A $& B $1")).toBe("Ask A $& B $1");
  });
  it("never names Mise in any guest string", () => {
    expect(JSON.stringify(en)).not.toMatch(/\bMise\b/);
    expect(JSON.stringify(ur)).not.toMatch(/\bMise\b/);
  });
  it("has the neutral scan-again text", () => {
    expect(en.ui.scanAgain).toBe("Scan the QR code on your table again.");
    expect(ur.ui.scanAgain).toBeTruthy();
  });
});
