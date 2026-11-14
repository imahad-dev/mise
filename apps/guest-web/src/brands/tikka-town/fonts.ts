import { Archivo, Bebas_Neue } from "next/font/google";

// Bold condensed shop-sign display and a sturdy grotesque text face. Free (OFL).
export const display = Bebas_Neue({ subsets: ["latin"], weight: "400", variable: "--brand-display-face", display: "swap" });
export const text = Archivo({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
