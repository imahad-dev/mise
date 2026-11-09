/** Header count on the kitchen screen: "1 ORDER ACTIVE", "3 ORDERS ACTIVE". */
export function activeLabel(n: number): string {
  return `${n} ${n === 1 ? "ORDER" : "ORDERS"} ACTIVE`;
}

/** Keeps "1 kg" on one line: a non-breaking space (U+00A0) between a number and its unit. */
export function keepUnits(text: string): string {
  return text.replace(/(\d) (kg|g|ml|l|pc|pcs)\b/gi, "$1\u00a0$2");
}
