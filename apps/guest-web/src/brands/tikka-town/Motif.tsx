import React from "react";

/** A ticket-stub edge under the masthead (punched half-circles); a loaded mustard skewer on the order bar.
 *  Drawn in pixels, so the holes and pieces keep their shape at any width. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" className="block h-3 w-full">
        <defs>
          <pattern id="tt-pieces" x="22" width="40" height="12" patternUnits="userSpaceOnUse">
            <rect x="2" y="1" width="10" height="10" rx="2" fill="var(--brand-spark)" />
            <rect x="22" y="1" width="10" height="10" rx="2" fill="var(--brand-accent)" />
          </pattern>
        </defs>
        <circle cx="6" cy="6" r="4" fill="none" stroke="var(--brand-spark)" strokeWidth="2" />
        <rect x="10" y="5" width="100%" height="2" fill="var(--brand-spark)" />
        <rect x="22" width="100%" height="12" fill="url(#tt-pieces)" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="-mt-px block h-2 w-full">
      <defs>
        {/* x="50%": the holes start at the centre, so both edges end the same way. */}
        <pattern id="tt-stub" x="50%" width="14" height="8" patternUnits="userSpaceOnUse">
          <rect width="14" height="8" fill="var(--brand-deep)" />
          <circle cx="7" cy="8" r="4" fill="var(--brand-surface)" />
        </pattern>
      </defs>
      <rect width="100%" height="8" fill="url(#tt-stub)" />
    </svg>
  );
}
