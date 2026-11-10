import { Jost, Karla } from "next/font/google";

// Light geometric display (calm tea room) and a soft text face. Free (OFL).
export const display = Jost({ subsets: ["latin"], weight: ["300", "400"], variable: "--brand-display-face", display: "swap" });
export const text = Karla({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
