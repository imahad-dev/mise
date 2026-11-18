import { describe, expect, it } from "vitest";
import { claimWelcome } from "./welcome";

function memoryStorage() {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
}

describe("claimWelcome", () => {
  it("plays once per visit", () => {
    const s = memoryStorage();
    expect(claimWelcome("visit-1", s)).toBe(true);
    expect(claimWelcome("visit-1", s)).toBe(false);
    expect(claimWelcome("visit-2", s)).toBe(true);
  });
  it("remembers a visit across page loads through storage", () => {
    const s = memoryStorage();
    s.setItem("welcome:visit-old", "1"); // played before a reload
    expect(claimWelcome("visit-old", s)).toBe(false);
  });
  it("plays once per page load when storage is missing", () => {
    expect(claimWelcome("no-storage", null)).toBe(true);
    expect(claimWelcome("no-storage", null)).toBe(false);
  });
  it("plays once per page load when storage throws (private mode, blocked)", () => {
    const broken = {
      getItem: () => { throw new Error("SecurityError"); },
      setItem: () => { throw new Error("QuotaExceededError"); },
    };
    expect(claimWelcome("broken", broken)).toBe(true);
    expect(claimWelcome("broken", broken)).toBe(false);
  });
  it("still plays when only writing fails", () => {
    const readOnly = { getItem: () => null, setItem: () => { throw new Error("QuotaExceededError"); } };
    expect(claimWelcome("read-only", readOnly)).toBe(true);
    expect(claimWelcome("read-only", readOnly)).toBe(false);
  });
  it("never plays without a visit id", () => {
    expect(claimWelcome("", memoryStorage())).toBe(false);
  });
});
