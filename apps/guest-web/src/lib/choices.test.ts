import { describe, expect, it } from "vitest";
import { addToCart } from "./cart";
import { getDictionary } from "../i18n";
import {
  cartChoiceText, defaultPicks, firstMissing, matchedAllergens, needsPage, pickedChoices, requirement, toggle, unitPrice, worstStatus,
  type CartChoice, type ChoiceGroup,
} from "./choices";

const c = (id: string, extra = {}) => ({
  id, label: id, price_delta: "0", allergens: [], is_vegetarian: true, is_vegan: true,
  available: true, is_default: false, allergen_status: "no_declared_match" as const,
  matched_allergens: [], ...extra,
});
const spice: ChoiceGroup = {
  id: "s", label: "Spice", kind: "pick", min_select: 1, max_select: 1, choices: [c("mild"), c("hot")],
};
const sugar: ChoiceGroup = {
  id: "u", label: "Sugar", kind: "pick", min_select: 1, max_select: 1,
  choices: [c("normal", { is_default: true }), c("none")],
};
const extras: ChoiceGroup = {
  id: "e", label: "Extras", kind: "add", min_select: 0, max_select: 2,
  choices: [c("milk", { price_delta: "0.50" }), c("shot", { price_delta: "0.80" }), c("oat")],
};

describe("dish page rules", () => {
  it("starts with available defaults only", () => {
    expect(defaultPicks([sugar, spice])).toEqual(["normal"]);
    const gone = { ...sugar, choices: [c("normal", { is_default: true, available: false })] };
    expect(defaultPicks([gone])).toEqual([]);
  });
  it("finds the first empty required group", () => {
    expect(firstMissing([sugar, spice], ["normal"])?.id).toBe("s");
    expect(firstMissing([sugar, spice], ["normal", "hot"])).toBeNull();
  });
  it("a radio group swaps, a checkbox group adds up to its maximum", () => {
    expect(toggle(spice, ["mild", "normal"], "hot")).toEqual(["normal", "hot"]);
    expect(toggle(extras, ["milk"], "shot")).toEqual(["milk", "shot"]);
    expect(toggle(extras, ["milk", "shot"], "oat")).toEqual(["milk", "shot"]);
    expect(toggle(extras, ["milk", "shot"], "milk")).toEqual(["shot"]);
  });
  it("an optional pick of one can be cleared and swapped", () => {
    const one = { ...extras, max_select: 1 };
    expect(toggle(one, ["milk"], "shot")).toEqual(["shot"]);
    expect(toggle(one, ["shot"], "shot")).toEqual([]);
  });
  it("ignores a sold-out choice or one from another group", () => {
    const gone = { ...extras, choices: [...extras.choices, c("cream", { available: false })] };
    expect(toggle(gone, ["milk"], "cream")).toEqual(["milk"]);
    expect(toggle(extras, ["milk"], "hot")).toEqual(["milk"]);
    expect(toggle(spice, ["mild"], "nope")).toEqual(["mild"]);
  });
  it("tapping the picked radio again keeps it picked", () => {
    expect(toggle(spice, ["normal", "hot"], "hot")).toEqual(["normal", "hot"]);
  });
  it("addToCart takes choices only as its own argument", () => {
    // Exhaustive: the build fails if the item type gains (or loses) a key.
    type Item = Parameters<typeof addToCart>[0];
    const keys: Record<keyof Item, true> = {
      menuItemId: true, name: true, price: true, notes: true, allergenStatus: true, matchedAllergens: true,
    };
    expect("choices" in keys).toBe(false);
  });
  it("adds prices to the base", () => {
    expect(unitPrice(3, [extras], ["milk", "shot"])).toBeCloseTo(4.3);
  });
  it("takes the worst allergen status of dish and picks", () => {
    const risky = { ...extras, choices: [c("milk", { allergen_status: "contains" })] };
    expect(worstStatus("no_declared_match", [risky], ["milk"])).toBe("contains");
    expect(worstStatus("unverified", [risky], [])).toBe("unverified");
  });
  it("+ adds in one tap only when defaults are enough and there are no sizes", () => {
    expect(needsPage({ options: [], choice_groups: [] })).toBe(false);
    expect(needsPage({ options: [], choice_groups: [sugar, extras] })).toBe(false);
    expect(needsPage({ options: [], choice_groups: [spice] })).toBe(true);
    expect(needsPage({ options: [{ id: "h", label: "Half", price: "1" }], choice_groups: [] })).toBe(true);
  });
  it("+ opens the page when a default costs money or carries an allergen warning", () => {
    const paid = { ...extras, choices: [c("milk", { is_default: true, price_delta: "0.50" })] };
    const risky = { ...extras, choices: [c("milk", { is_default: true, allergen_status: "unverified" })] };
    const paidButGone = {
      ...extras, choices: [c("milk", { is_default: true, available: false, price_delta: "0.50" })],
    };
    expect(needsPage({ choice_groups: [sugar, paid] })).toBe(true);
    expect(needsPage({ choice_groups: [sugar, risky] })).toBe(true);
    expect(needsPage({ choice_groups: [sugar, paidButGone] })).toBe(false);
  });
  it("adds the picked choices' allergen matches to the dish's, once each", () => {
    const milky = {
      ...extras,
      choices: [c("milk", { matched_allergens: ["milk"] }), c("oat", { matched_allergens: ["gluten"] })],
    };
    expect(matchedAllergens(["milk"], [milky], ["milk"])).toEqual(["milk"]);
    expect(matchedAllergens(undefined, [milky], ["milk", "oat"])).toEqual(["milk", "gluten"]);
    expect(matchedAllergens(["eggs"], [milky], [])).toEqual(["eggs"]);
  });
  it("says what a group needs in words", () => {
    expect(requirement(spice)).toEqual({ key: "chooseOne", n: 1 });
    expect(requirement(extras)).toEqual({ key: "upTo", n: 2 });
    expect(requirement({ ...extras, max_select: 1 })).toEqual({ key: "optional", n: 1 });
  });
  it("lists picks in menu order for the cart", () => {
    expect(pickedChoices([extras], ["shot", "milk"]).map((p) => p.id)).toEqual(["milk", "shot"]);
  });
});

describe("cartChoiceText", () => {
  const line: CartChoice[] = [
    { id: "hot", group: "Spice", kind: "pick", label: "Hot", priceDelta: 0 },
    { id: "shot", group: "Extras", kind: "add", label: "Extra shot", priceDelta: 150 },
    { id: "onion", group: "Leave out", kind: "leave_out", label: "Onions", priceDelta: 0 },
  ];
  const money = (n: number) => `Rs ${n}`;

  it("reads like the bill in English", () => {
    expect(cartChoiceText(line, money, getDictionary("en").dish.leaveOut)).toBe("Hot, Extra shot +Rs 150, No onions");
  });

  it("uses the Italian leave-out wording", () => {
    expect(cartChoiceText(line, money, getDictionary("it").dish.leaveOut)).toBe("Hot, Extra shot +Rs 150, Senza onions");
  });
});
