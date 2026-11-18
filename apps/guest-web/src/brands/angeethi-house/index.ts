import type { BrandPackage } from "../types";
import { display, text } from "./fonts";
import { Loader } from "./Loader";
import { Motif } from "./Motif";
import { Welcome } from "./Welcome";

export const brand: BrandPackage = { fontClass: `${display.variable} ${text.variable}`, Motif, Welcome, Loader };
