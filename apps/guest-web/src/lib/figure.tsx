import React from "react";

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
