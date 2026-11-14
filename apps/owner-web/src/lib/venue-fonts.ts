import { Anton, Bebas_Neue, El_Messiri, Jost } from "next/font/google";

// Display faces of the venue brands, for the printed QR cards and sample bill only.
const anton = Anton({ subsets: ["latin"], weight: "400", display: "swap" });
const jost = Jost({ subsets: ["latin"], weight: ["300", "400"], display: "swap" });
const messiri = El_Messiri({ subsets: ["latin", "arabic"], weight: ["600"], display: "swap" });
const bebas = Bebas_Neue({ subsets: ["latin"], weight: "400", display: "swap" });

export const VENUE_DISPLAY_CLASS: Record<string, string> = {
  "angeethi-house": anton.className,
  "kehwa-and-crumb": jost.className,
  "noor-and-zaatar": messiri.className,
  "tikka-town": bebas.className,
};
