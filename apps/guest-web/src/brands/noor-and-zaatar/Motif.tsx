import React from "react";
import { FLAME, flameAt } from "./logo";

/** An arcade of arches under the masthead, every other one holding the logo's flame; a saffron thread
 *  with one flame on the order bar. Drawn in pixels, so the arches keep their shape at any width. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  // One id per render, so two motifs on a page never share a pattern; React's id characters are not safe in url(#…).
  const id = `nz${React.useId().replace(/[^\w-]/g, "")}-arcade`;
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" className="block h-2.5 w-full overflow-visible">
        <line x1="0" y1="5" x2="100%" y2="5" stroke="var(--brand-spark)" strokeWidth="1.5" opacity="0.55" />
        <svg x="50%" overflow="visible">
          <rect x="-9" y="0" width="18" height="10" fill="var(--brand-card)" />
          <path d={FLAME} transform={flameAt(0, 10, 0.19)} fill="var(--brand-spark)" />
        </svg>
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="block h-[18px] w-full">
      <defs>
        {/* x="50%": the tiles start at the centre, so both edges cut the arcade the same way. */}
        <pattern id={id} x="50%" width="64" height="18" patternUnits="userSpaceOnUse">
          <path d="M7 18V10a9 8 0 0 1 18 0v8M39 18V10a9 8 0 0 1 18 0v8" fill="none" stroke="var(--brand-spark)" strokeWidth="1.5" />
          <path d={FLAME} transform={flameAt(16, 16, 0.13)} fill="var(--brand-spark)" />
        </pattern>
      </defs>
      <rect width="100%" height="18" fill={`url(#${id})`} />
    </svg>
  );
}
