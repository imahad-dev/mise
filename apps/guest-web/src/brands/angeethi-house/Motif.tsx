import React from "react";

/** A bed of coals: ember dots under the masthead, a thin glowing strip on the order bar. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-1 w-full">
        <defs>
          <linearGradient id="ah-ember" x1="0" x2="1">
            <stop offset="0" stopColor="var(--brand-deep)" />
            <stop offset="0.5" stopColor="var(--brand-spark)" />
            <stop offset="1" stopColor="var(--brand-deep)" />
          </linearGradient>
        </defs>
        <rect width="100" height="4" fill="url(#ah-ember)" />
      </svg>
    );
  }
  const coals = [8, 19, 31, 44, 56, 69, 81, 92];
  return (
    <svg aria-hidden="true" viewBox="0 0 100 10" className="block h-3 w-full">
      {coals.map((x, i) => (
        <circle key={x} cx={x} cy={i % 2 ? 6 : 4} r={i % 3 ? 1.6 : 2.2} fill="var(--brand-spark)" opacity={i % 3 ? 0.55 : 0.9} />
      ))}
    </svg>
  );
}
