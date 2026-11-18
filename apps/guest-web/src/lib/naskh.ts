import { Noto_Naskh_Arabic } from "next/font/google";

/** Urdu and Arabic text (Naskh: a third of Nastaliq's size, no clipping; research urdu_ui.md).
 *  Not preloaded, and limited to Arabic code points, so English pages never download it. */
export const naskh = Noto_Naskh_Arabic({
  subsets: ["arabic"],
  weight: ["400", "700"],
  display: "swap",
  preload: false,
  variable: "--font-naskh",
});
