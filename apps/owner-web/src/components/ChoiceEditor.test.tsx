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

const editor = (groups: OwnerChoiceGroup[], onChanged = () => {}) => (
  <ChoiceEditor slug="v" itemId="i" groups={groups} money={money} onChanged={onChanged} />
);

describe("ChoiceEditor", () => {
  it("lists groups and their choices with prices and allergens", () => {
    render(editor([GROUP]));
    expect(screen.getByText(/Extras/)).toBeTruthy();
    expect(screen.getByText(/Extra milk/)).toBeTruthy();
    expect(screen.getByText(/\+£0\.50/)).toBeTruthy();
    expect(screen.getByText(/Allergens: milk/)).toBeTruthy();
    expect(screen.getByText(/Unconfirmed/)).toBeTruthy();
  });

  it("shows a note instead of allergen toggles for leave-outs", () => {
    render(editor([LEAVE_OUT]));
    expect(screen.getByText("Leave-outs need no allergen check")).toBeTruthy();
    expect(screen.queryByText("Vegetarian")).toBeNull();
    expect(screen.queryByText("Vegan")).toBeNull();
    expect(screen.queryByText(/Allergens confirmed/)).toBeNull();
  });

  it("shows the server's message as it comes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "A label can't promise safety" }), { status: 422 })),
    );
    render(editor([GROUP]));
    fireEvent.click(screen.getByLabelText("On sale"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("A label can't promise safety"));
  });

  it("moves a group by swapping positions with two saves", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(editor([GROUP, LEAVE_OUT], onChanged));
    fireEvent.click(screen.getByLabelText("Move Extras down"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toBe("/api/restaurants/v/choice-groups/g1");
    expect(calls[0][1].body).toBe(JSON.stringify({ sort_order: 1 }));
    expect(calls[1][0]).toBe("/api/restaurants/v/choice-groups/g2");
    expect(calls[1][1].body).toBe(JSON.stringify({ sort_order: 0 }));
  });
});
