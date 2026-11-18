import { describe, expect, it } from "vitest";
import { mainIngredients } from "./ingredients";

describe("mainIngredients", () => {
  it("shows the first ingredients, capitalised, as tags", () => {
    expect(mainIngredients(["espresso", "water"])).toEqual(["Espresso", "Water"]);
  });
  it("keeps at most four, in the menu's own order", () => {
    expect(mainIngredients(["a", "b", "c", "d", "e", "f"])).toEqual(["A", "B", "C", "D"]);
    expect(mainIngredients(["milk", "tea", "sugar"], 2)).toEqual(["Milk", "Tea"]);
  });
  it("drops blanks and repeats, whatever their case or spacing", () => {
    expect(mainIngredients(["  milk ", "", "Milk", "   ", "condensed milk"])).toEqual(["Milk", "Condensed milk"]);
  });
  it("returns nothing for a dish without ingredients", () => {
    expect(mainIngredients([])).toEqual([]);
    expect(mainIngredients(undefined)).toEqual([]);
  });
  it("leaves names that already start with a capital or a digit alone", () => {
    expect(mainIngredients(["Kashmiri chai", "2 eggs"])).toEqual(["Kashmiri chai", "2 eggs"]);
  });
});
