// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { KitchenChoices } from "./KitchenChoices";

afterEach(cleanup);

describe("KitchenChoices", () => {
  it("shows picks with their group, extras plainly, and leave-outs loud", () => {
    render(
      <KitchenChoices
        choices={[
          { choice_id: "a", group: "Spice", kind: "pick", label: "Medium", price_delta: "0" },
          { choice_id: "b", group: "Extras", kind: "add", label: "Extra milk", price_delta: "0.50" },
          { choice_id: "c", group: "Leave out", kind: "leave_out", label: "Onions", price_delta: "0" },
        ]}
      />,
    );
    expect(screen.getByText("Spice: Medium")).toBeTruthy();
    expect(screen.getByText("Extra milk")).toBeTruthy();
    const no = screen.getByText("NO Onions");
    expect(no.className).toContain("uppercase");
    expect(no.className).toContain("text-kds-warn");
  });
  it("renders nothing without choices", () => {
    const { container } = render(<KitchenChoices />);
    expect(container.innerHTML).toBe("");
  });
});
