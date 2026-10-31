// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { FloorResponse, FloorTile } from "../../../lib/floor";
import FloorPage from "./page";

const tile: FloorTile = {
  table_id: "t1", label: "T1", state: "approval_needed", level: "amber", since: null, reason: null,
  reason_label: null, running_total: null, bill_id: null, call_id: null, sitting_open: true,
  waiting_for_open: false, pending_order_id: "o1", pending_order_ids: ["o1"], pending_order_total: "500.00",
  pending_order_items: 2,
};
const floor: FloorResponse = {
  tiles: [tile], counts: { red: 0, amber: 1 }, thresholds: {}, server_time: new Date().toISOString(),
  service_extra_label: null, pay_forward_balance: 0,
};

let finishRefetch = () => {};
const refetch = vi.fn(() => new Promise<void>((r) => (finishRefetch = r)));

vi.mock("../../../lib/venue", () => ({
  useVenue: () => ({ venue: { slug: "v", currency: "PKR" } }),
  useSlugRef: (slug: string) => ({ current: slug }),
}));
vi.mock("../../../hooks/use-sse", () => ({
  useSse: () => ({ data: { floor, loadedAt: Date.now() }, error: null, refetch }),
}));
vi.mock("../../../components/PayForwardTile", () => ({ PayForwardTile: () => null }));

afterEach(() => vi.unstubAllGlobals());

describe("Floor approve", () => {
  it("keeps the buttons disabled until the reload, then shows the server's 409 text", async () => {
    let answer: (res: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((r) => (answer = r)));
    vi.stubGlobal("fetch", fetchMock);
    render(<FloorPage />);

    const approve = screen.getByRole("button", { name: "Approve, T1" });
    const notNow = screen.getByRole("button", { name: "Not now, T1" });
    fireEvent.click(approve);
    await waitFor(() => expect(approve.hasAttribute("disabled")).toBe(true));
    expect(notNow.hasAttribute("disabled")).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith("/api/restaurants/v/tables/t1/approve", expect.objectContaining({ method: "POST" }));

    answer(new Response(JSON.stringify({ detail: "This order has changed" }), { status: 409 }));
    await waitFor(() => expect(refetch).toHaveBeenCalled());
    expect(approve.hasAttribute("disabled")).toBe(true); // still waiting for the Floor to reload

    finishRefetch();
    expect(await screen.findByText("T1: This order has changed")).toBeTruthy();
    expect(approve.hasAttribute("disabled")).toBe(false);
  });
});
