import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CodeEntry, type CodeEntryProps } from "./CodeEntry";
import { en, it as itDict } from "../i18n";

const view = (p: Partial<CodeEntryProps>) =>
  renderToStaticMarkup(
    <CodeEntry lang="en" code="" onChange={() => {}} message={null} lockedFor={0} busy={false} {...p} />,
  );

describe("CodeEntry", () => {
  it("shows four numeric boxes, the first one ready for the phone's autofill", () => {
    const html = view({ code: "12" });
    expect(html.match(/inputMode="numeric"/g)).toHaveLength(4);
    expect(html.match(/autoComplete="one-time-code"/g)).toHaveLength(1);
    expect(html).toContain('aria-label="Number 1 of 4"');
    expect(html).toContain('value="1"');
    expect(html).toContain('value="2"');
  });
  it("says a wrong number plainly", () => {
    expect(view({ message: en.order.numberWrong })).toContain("That number didn&#x27;t match. Please ask your waiter.");
  });
  it("counts down while locked, with the boxes disabled", () => {
    const html = view({ lockedFor: 42, message: en.order.tooManyTries });
    expect(html).toContain("You can try again in 42 s");
    expect(html.match(/disabled=""/g)).toHaveLength(4);
  });
  it("uses only everyday words on screen", () => {
    for (const dict of [en, itDict]) {
      const text = Object.values(dict.order).join(" ").toLowerCase();
      for (const word of ["server", "session", "sitting", "approval", "pending", "code", "error", "sessione"]) {
        expect(text).not.toContain(word);
      }
    }
  });
});
