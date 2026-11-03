// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { ServiceReportCard } from "./ServiceReportCard";

afterEach(() => vi.unstubAllGlobals());

describe("ServiceReportCard", () => {
  it("renders nothing for staff (403)", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: "Owners only" }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<ServiceReportCard slug="v" />);
    await waitFor(() => expect(container.innerHTML).toBe(""));
    expect(fetchMock).toHaveBeenCalledWith("/api/restaurants/v/service-report");
  });
});
