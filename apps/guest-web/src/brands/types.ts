import type { ComponentType } from "react";

export interface BrandPackage {
  /** next/font variable classes for the display and text faces. */
  fontClass: string;
  /** Static SVG decoration; no animation library. */
  Motif: ComponentType<{ variant: "masthead" | "bar" }>;
  /** About 2 s; calls onDone when finished. */
  Welcome: ComponentType<{ name: string; onDone: () => void }>;
  Loader: ComponentType<{ label: string; size?: "sm" | "md" }>;
}
