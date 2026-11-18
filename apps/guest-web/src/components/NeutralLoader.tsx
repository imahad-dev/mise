import React from "react";

export function NeutralLoader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-4 w-4 border-2" : "h-8 w-8 border-[3px]";
  return (
    <span role="status" className="inline-flex items-center gap-2 text-ink-muted">
      <span aria-hidden className={`${box} animate-spin rounded-full border-line border-t-ink`} />
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
