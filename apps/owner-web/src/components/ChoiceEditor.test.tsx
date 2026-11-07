// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChoiceEditor, type OwnerChoice, type OwnerChoiceGroup } from "./ChoiceEditor";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const money = (n: number) => `£${n.toFixed(2)}`;

const CHOICE: OwnerChoice = {
  id: "c1",
  label: "Extra milk",
  price_delta: "0.50",
  cost_delta: "0.10",
  allergens: ["milk"],
  allergen_verified: false,
  is_vegetarian: true,
  is_vegan: false,
  available: true,
  is_default: false,
  sort_order: 0,
};

const GROUP: OwnerChoiceGroup = {
  id: "g1",
  label: "Extras",
  kind: "add",
  min_select: 0,
  max_select: 3,
  sort_order: 0,
  choices: [CHOICE],
};

const LEAVE_OUT: OwnerChoiceGroup = {
  id: "g2",
  label: "Without",
  kind: "leave_out",
  min_select: 0,
  max_select: 5,
  sort_order: 1,
  choices: [
    { ...CHOICE, id: "c2", label: "Onions", price_delta: "0", allergens: [], allergen_verified: true, is_vegan: true },
  ],
};

const editor = (groups: OwnerChoiceGroup[], onChanged: () => void | Promise<void> = () => {}) => (
  <ChoiceEditor slug="v" itemId="i" groups={groups} money={money} onChanged={onChanged} />
);

const ok = () => new Response("{}", { status: 200 });
type Mock = { mock: { calls: unknown[][] } };
const calls = (m: Mock) => m.mock.calls as unknown as [string, RequestInit][];
const bodies = (m: Mock) => calls(m).map(([, init]) => JSON.parse(String(init.body)));
const group = (id: string, label: string, sort_order: number, choices: OwnerChoice[] = []): OwnerChoiceGroup => ({
  ...GROUP, id, label, sort_order, choices,
});
const choice = (id: string, label: string, sort_order: number): OwnerChoice => ({ ...CHOICE, id, label, sort_order });

describe("ChoiceEditor", () => {
  it("lists groups and their choices with prices, cost and allergens", () => {
    render(editor([GROUP]));
    expect(screen.getByText(/Extras · Add extras/)).toBeTruthy();
    expect(screen.getByText(/\+£0\.50/)).toBeTruthy();
    expect(screen.getByText(/cost £0\.10/)).toBeTruthy();
    expect(screen.getByText(/Allergens: milk/)).toBeTruthy();
    expect(screen.getByText(/Unconfirmed/)).toBeTruthy();
  });

  it("shows a note instead of allergen toggles for leave-outs", () => {
    render(editor([LEAVE_OUT]));
    expect(screen.getByText("Leave-outs need no allergen check")).toBeTruthy();
    expect(screen.queryByText("Vegetarian")).toBeNull();
    expect(screen.queryByText("Vegan")).toBeNull();
    expect(screen.queryByText(/Allergens confirmed/)).toBeNull();
    expect(screen.queryByLabelText(/Price of/)).toBeNull();
  });

  it("warns when a required group has nothing on sale", () => {
    const warn = "Guests can't order this dish until this group has a choice.";
    const required = { ...GROUP, min_select: 1 };
    render(editor([{ ...required, choices: [{ ...CHOICE, available: false }] }]));
    expect(screen.getByText(warn)).toBeTruthy();
    cleanup();
    render(editor([required]));
    expect(screen.queryByText(warn)).toBeNull();
    cleanup();
    render(editor([{ ...GROUP, choices: [] }]));
    expect(screen.queryByText(warn)).toBeNull();
  });

  it("shows the server's message as it comes, and keeps it until a save works", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "A label can't promise safety" }), { status: 422 }))
      .mockResolvedValue(ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([GROUP]));
    fireEvent.click(screen.getByLabelText("On sale: Extra milk"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("A label can't promise safety"));
    await waitFor(() => expect(screen.getByLabelText("On sale: Extra milk").matches(":disabled")).toBe(false));
    fireEvent.click(screen.getByLabelText("On sale: Extra milk"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("shows a list-shaped 422 message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: [{ msg: "Value error, Too many choices" }] }), { status: 422 })),
    );
    render(editor([GROUP]));
    fireEvent.click(screen.getByLabelText("On sale: Extra milk"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Too many choices"));
  });

  it("an allergen tick sends only the allergens, and confirm only the flag", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([GROUP]));
    fireEvent.click(screen.getByLabelText("gluten in Extra milk"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)[0][0]).toBe("/api/restaurants/v/choices/c1");
    expect(bodies(fetchMock)[0]).toEqual({ allergens: ["milk", "gluten"] });
    await waitFor(() => expect(screen.getByLabelText("Allergens confirmed for Extra milk").matches(":disabled")).toBe(false));
    fireEvent.click(screen.getByLabelText("Allergens confirmed for Extra milk"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(bodies(fetchMock)[1]).toEqual({ allergen_verified: true });
  });

  it("locks the editor while a save is in flight, so a second tick is refused", async () => {
    let finish: (r: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((r) => (finish = r)));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(editor([GROUP]));
    fireEvent.click(screen.getByLabelText("gluten in Extra milk"));
    await waitFor(() => expect(container.querySelector("[aria-busy='true']")).toBeTruthy());
    expect(screen.getByLabelText("eggs in Extra milk").matches(":disabled")).toBe(true);
    fireEvent.click(screen.getByLabelText("eggs in Extra milk"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(ok());
    await waitFor(() => expect(container.querySelector("[aria-busy='true']")).toBeNull());
  });

  it("sends a double-clicked add once", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([GROUP]));
    fireEvent.change(screen.getByLabelText("New choice name for Extras"), { target: { value: "Oat milk" } });
    const add = screen.getByLabelText("Add choice to Extras");
    fireEvent.click(add);
    fireEvent.click(add);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a group with the preset for its kind and no position", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([]));
    fireEvent.change(screen.getByLabelText("New group"), { target: { value: "Spice" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "pick" } });
    fireEvent.click(screen.getByText("Add group"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)[0][0]).toBe("/api/restaurants/v/menu-items/i/choice-groups");
    expect(bodies(fetchMock)[0]).toEqual({ label: "Spice", kind: "pick", min_select: 1, max_select: 1 });
  });

  it("creates a leave-out with no price fields", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([LEAVE_OUT]));
    expect(screen.queryByLabelText("New choice price for Without")).toBeNull();
    fireEvent.change(screen.getByLabelText("New choice name for Without"), { target: { value: "Garlic" } });
    fireEvent.click(screen.getByLabelText("Add choice to Without"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodies(fetchMock)[0]).toEqual({ label: "Garlic" });
  });

  it("creates an extra with price and cost", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([GROUP]));
    fireEvent.change(screen.getByLabelText("New choice name for Extras"), { target: { value: "Oat milk" } });
    fireEvent.change(screen.getByLabelText("New choice price for Extras"), { target: { value: "0.8" } });
    fireEvent.click(screen.getByLabelText("Add choice to Extras"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodies(fetchMock)[0]).toEqual({ label: "Oat milk", price_delta: "0.8", cost_delta: "0" });
  });

  it("edits a group's name and limits", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([GROUP]));
    fireEvent.change(screen.getByLabelText("Name of Extras"), { target: { value: "Add-ons" } });
    fireEvent.change(screen.getByLabelText("Minimum for Extras"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Maximum for Extras"), { target: { value: "2" } });
    fireEvent.click(screen.getByLabelText("Save Extras"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)[0][0]).toBe("/api/restaurants/v/choice-groups/g1");
    expect(bodies(fetchMock)[0]).toEqual({ label: "Add-ons", min_select: 1, max_select: 2 });
  });

  it("edits a choice's name, price and cost", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([GROUP]));
    fireEvent.change(screen.getByLabelText("Price of Extra milk"), { target: { value: "0.70" } });
    fireEvent.change(screen.getByLabelText("Cost of Extra milk"), { target: { value: "0.2" } });
    fireEvent.click(screen.getByLabelText("Save Extra milk"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)[0][0]).toBe("/api/restaurants/v/choices/c1");
    expect(bodies(fetchMock)[0]).toEqual({ label: "Extra milk", price_delta: "0.70", cost_delta: "0.2" });
  });

  it("renumbers every group when moving, even with tied positions", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    render(editor([group("a", "A", 0), group("b", "B", 0), group("c", "C", 5)]));
    fireEvent.click(screen.getByLabelText("Move A down"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(calls(fetchMock).map(([u]) => u)).toEqual([
      "/api/restaurants/v/choice-groups/b",
      "/api/restaurants/v/choice-groups/a",
      "/api/restaurants/v/choice-groups/c",
    ]);
    expect(bodies(fetchMock)).toEqual([{ sort_order: 0 }, { sort_order: 1 }, { sort_order: 2 }]);
  });

  it("renumbers every choice when moving one up", async () => {
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    const g = group("g", "G", 0, [choice("x", "X", 3), choice("y", "Y", 3), choice("z", "Z", 9)]);
    render(editor([g]));
    fireEvent.click(screen.getByLabelText("Move Z up"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(calls(fetchMock).map(([u]) => u)).toEqual([
      "/api/restaurants/v/choices/x",
      "/api/restaurants/v/choices/z",
      "/api/restaurants/v/choices/y",
    ]);
    expect(bodies(fetchMock)).toEqual([{ sort_order: 0 }, { sort_order: 1 }, { sort_order: 2 }]);
  });

  it("disables up on the first and down on the last", () => {
    const g = group("g", "G", 0, [choice("x", "X", 0), choice("y", "Y", 1)]);
    render(editor([g, group("h", "H", 1)]));
    const off = (name: string) => screen.getByLabelText(name).matches(":disabled");
    expect(off("Move G up")).toBe(true);
    expect(off("Move G down")).toBe(false);
    expect(off("Move H down")).toBe(true);
    expect(off("Move X up")).toBe(true);
    expect(off("Move Y down")).toBe(true);
    expect(off("Move X down")).toBe(false);
  });

  it("moves focus to the group heading after a choice delete, and the editor heading after a group delete", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok()));
    render(editor([GROUP]));
    fireEvent.click(screen.getByLabelText("Delete Extra milk"));
    await waitFor(() => expect(document.activeElement?.id).toBe("choice-group-g1"));
    await waitFor(() => expect(screen.getByLabelText("Delete Extras").matches(":disabled")).toBe(false));
    fireEvent.click(screen.getByLabelText("Delete Extras"));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Choices"));
  });
});
