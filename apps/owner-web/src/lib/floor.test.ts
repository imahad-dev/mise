import { describe, expect, it } from "vitest";
import {
  elapsed,
  formatElapsed,
  isStale,
  levelClass,
  payForwardText,
  sortTiles,
  stateLabel,
  type FloorTile,
} from "./floor";

const tile = (label: string, level: FloorTile["level"]): FloorTile => ({
  table_id: label, label, state: "seated", level, since: null, reason: null, reason_label: null,
  running_total: null, bill_id: null, call_id: null,
});

describe("floor helpers", () => {
  it("says how many pay-it-forward chai are waiting", () => {
    expect(payForwardText(0)).toBe("No chai waiting");
    expect(payForwardText(3)).toBe("Pay-it-forward chai: 3 waiting");
  });
  it("measures elapsed time on the server clock", () => {
    const since = "2026-10-25T12:00:00Z";
    const server = "2026-10-25T12:05:00Z";
    const loadedAt = Date.parse("2026-10-25T12:15:00Z"); // client clock 10 min fast
    expect(elapsed(since, server, loadedAt + 3_000, loadedAt)).toBe(303_000);
    expect(elapsed("2026-10-25T12:06:00Z", server, loadedAt, loadedAt)).toBe(0);
  });
  it("formats m:ss", () => {
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(3_599_999)).toBe("59:59");
  });
  it("labels states in words", () => {
    expect(stateLabel("seated")).toBe("Seated, no order");
    expect(stateLabel("needs_clearing")).toBe("Needs clearing");
    expect(stateLabel("called")).toBe("Waiter called");
  });
  it("keeps red, amber, none order and the label order inside a level", () => {
    const sorted = sortTiles([tile("T1", "none"), tile("T2", "amber"), tile("T3", "red"), tile("T4", "amber")]);
    expect(sorted.map((t) => t.label)).toEqual(["T3", "T2", "T4", "T1"]);
  });
  it("warns only after 45 s without a successful load", () => {
    expect(isStale(45_000)).toBe(false);
    expect(isStale(45_001)).toBe(true);
  });
  it("maps levels to the existing danger and warn tokens", () => {
    expect(levelClass("red")).toContain("bg-danger-bg");
    expect(levelClass("amber")).toContain("bg-warn-bg");
    expect(levelClass("none")).toBe("");
  });
});
