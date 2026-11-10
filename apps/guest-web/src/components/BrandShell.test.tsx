// @vitest-environment jsdom
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const Boom = () => {
  throw new Error("welcome crashed");
};
const pkg = (Welcome: React.ComponentType<{ name: string; onDone: () => void }>) => ({
  fontClass: "",
  Motif: () => null,
  Loader: () => null,
  Welcome,
});

vi.mock("../brands", () => ({
  loadBrand: (slug: string) => {
    if (slug === "broken") return Promise.reject(new Error("chunk failed"));
    if (slug === "hang") return new Promise(() => {});
    if (slug === "plays") return Promise.resolve(pkg(({ name }) => <p>Welcome to {name}</p>));
    if (slug === "crashes") return Promise.resolve(pkg(Boom));
    return Promise.resolve(null);
  },
}));

import { BrandShell, useVenue } from "./BrandShell";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

function Name() {
  return <p>{useVenue().name}</p>;
}

describe("BrandShell", () => {
  it("gives its children the venue name and the brand's variables", () => {
    const { container } = render(
      <BrandShell venue={{ slug: "angeethi-house", name: "Angeethi House" }}>
        <Name />
      </BrandShell>,
    );
    expect(screen.getByText("Angeethi House")).toBeTruthy();
    const root = container.querySelector("[data-brand]") as HTMLElement;
    expect(root.dataset.brand).toBe("angeethi-house");
    expect(root.style.getPropertyValue("--brand-accent")).toBe("#7f011f");
  });
  it("renders neutrally for a venue without a brand, still naming it", () => {
    const { container } = render(
      <BrandShell venue={{ slug: "new-venue", name: "New Venue" }}>
        <Name />
      </BrandShell>,
    );
    expect(screen.getByText("New Venue")).toBeTruthy();
    expect((container.querySelector("[data-brand]") as HTMLElement).dataset.brand).toBe("neutral");
  });
  it("keeps the page and skips the welcome when the brand package fails to load", async () => {
    render(
      <BrandShell venue={{ slug: "broken", name: "Broken Venue" }} welcomeFor="visit-1">
        <Name />
      </BrandShell>,
    );
    await waitFor(() => expect(document.querySelector('[data-welcome="done"]')).toBeTruthy());
    expect(screen.getByText("Broken Venue")).toBeTruthy();
    expect(screen.queryByTestId("welcome")).toBeNull();
  });

  describe("welcome", () => {
    const shell = (slug: string, visit: string) => (
      <BrandShell venue={{ slug, name: "Plays Venue" }} welcomeFor={visit}>
        <Name />
      </BrandShell>
    );
    const state = () => (document.querySelector("[data-welcome]") as HTMLElement).dataset.welcome;
    const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

    it("shows the welcome with the venue name, closes itself at 3 s", async () => {
      vi.useFakeTimers();
      render(shell("plays", "v-timer"));
      await settle();
      expect(screen.getByTestId("welcome").textContent).toContain("Welcome to Plays Venue");
      act(() => { vi.advanceTimersByTime(2900); });
      expect(screen.queryByTestId("welcome")).toBeTruthy();
      act(() => { vi.advanceTimersByTime(200); });
      expect(screen.queryByTestId("welcome")).toBeNull();
      expect(state()).toBe("done");
    });
    it("closes at once on a tap", async () => {
      vi.useFakeTimers();
      render(shell("plays", "v-tap"));
      await settle();
      fireEvent.click(screen.getByTestId("welcome"));
      expect(screen.queryByTestId("welcome")).toBeNull();
      expect(state()).toBe("done");
    });
    it("skips a welcome that throws and keeps the page", async () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      render(shell("crashes", "v-crash"));
      await waitFor(() => expect(state()).toBe("done"));
      expect(screen.queryByTestId("welcome")).toBeNull();
      expect(screen.getByText("Plays Venue")).toBeTruthy();
    });
    it("ends done after 3 s when the brand request never resolves", async () => {
      vi.useFakeTimers();
      render(shell("hang", "v-hang"));
      await settle();
      expect(state()).toBe("pending");
      act(() => { vi.advanceTimersByTime(3100); });
      expect(state()).toBe("done");
      expect(screen.queryByTestId("welcome")).toBeNull();
    });
    it("does not show it a second time for the same visit", async () => {
      render(shell("plays", "v-twice"));
      await waitFor(() => expect(screen.getByTestId("welcome")).toBeTruthy());
      cleanup();
      render(shell("plays", "v-twice"));
      await waitFor(() => expect(state()).toBe("done"));
      expect(screen.queryByTestId("welcome")).toBeNull();
    });
  });
});
