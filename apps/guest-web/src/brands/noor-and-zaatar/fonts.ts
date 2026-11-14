import { El_Messiri, Figtree } from "next/font/google";

// Display with Latin and Arabic glyphs (logo band and Arabic headings share it) and a clean text face. Free (OFL).
export const display = El_Messiri({ subsets: ["latin", "arabic"], weight: ["600"], variable: "--brand-display-face", display: "swap" });
export const text = Figtree({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
