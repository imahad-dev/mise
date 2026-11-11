import React from "react";
import { choiceLine, type LineChoice } from "ui";

/** Fills `{token}` placeholders with values; each value gets the fixed money face, the sentence
 *  keeps the venue's. Unknown tokens stay visible as text. Values are never parsed. */
export function figureParts(template: string, values: Record<string, string>): React.ReactNode[] {
  return template.split(/(\{\w+\})/).map((part, i) => {
    const key = part.slice(1, -1);
    return /^\{\w+\}$/.test(part) && Object.prototype.hasOwnProperty.call(values, key) ? (
      <span key={i} className="figure">{values[key]}</span>
    ) : (
      part
    );
  });
}

/** The choices of a line as one `{p0}, {p1}` template plus its amounts, so `+price` renders in the money face.
 *  Same text as `choiceLine` joined with ", "; `choiceLine` itself is shared with owner-web and unchanged. */
export function choicesParts(
  choices: LineChoice[],
  money: (n: number) => string,
  noLabel: string,
): { template: string; values: Record<string, string> } {
  const values: Record<string, string> = {};
  const template = choices
    .map((c) =>
      choiceLine(c, (n) => {
        const key = `p${Object.keys(values).length}`;
        values[key] = money(n);
        return `{${key}}`;
      }, noLabel),
    )
    .join(", ");
  return { template, values };
}

/** `figureParts` for a `{ template, values }` pair, as `choicesParts`, `claimParts` and `paidParts` return. */
export const figureSentence = (p: { template: string; values: Record<string, string> }) => figureParts(p.template, p.values);
