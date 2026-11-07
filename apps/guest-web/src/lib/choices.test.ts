import { describe, expect, it } from "vitest";
import {
  defaultPicks, firstMissing, needsPage, pickedChoices, requirement, toggle, unitPrice, worstStatus,
  type ChoiceGroup,
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
  it("says what a group needs in words", () => {
    expect(requirement(spice)).toEqual({ key: "chooseOne", n: 1 });
    expect(requirement(extras)).toEqual({ key: "upTo", n: 2 });
    expect(requirement({ ...extras, max_select: 1 })).toEqual({ key: "optional", n: 1 });
  });
  it("lists picks in menu order for the cart", () => {
    expect(pickedChoices([extras], ["shot", "milk"]).map((p) => p.id)).toEqual(["milk", "shot"]);
  });
});
