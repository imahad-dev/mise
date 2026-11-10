import React from "react";

/** Crumbs: a scatter under the masthead, a dotted line on the order bar. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-1 w-full">
        <line x1="0" y1="2" x2="100" y2="2" stroke="var(--brand-spark)" strokeWidth="1.5" strokeDasharray="1 3" strokeLinecap="round" />
      </svg>
    );
  }
  const crumbs: [number, number, number][] = [
    [7, 4, 1.2], [16, 7, 0.8], [27, 3, 1], [41, 6, 1.4], [55, 4, 0.9], [63, 8, 1.1], [78, 5, 0.8], [90, 3, 1.3],
  ];
  return (
    <svg aria-hidden="true" viewBox="0 0 100 10" className="block h-3 w-full">
      {crumbs.map(([x, y, r]) => (
        <circle key={x} cx={x} cy={y} r={r} fill="var(--brand-spark)" opacity={0.8} />
      ))}
    </svg>
  );
}
