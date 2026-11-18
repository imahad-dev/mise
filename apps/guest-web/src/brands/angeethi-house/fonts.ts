import { Anton, Work_Sans } from "next/font/google";

// Heavy condensed display (coal-grill signboard) and a plain working text face. Free (OFL).
export const display = Anton({ subsets: ["latin"], weight: "400", variable: "--brand-display-face", display: "swap" });
export const text = Work_Sans({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
