export interface LineChoice {
  kind: "pick" | "add" | "leave_out";
  label: string;
  price_delta: string | number;
}

/** `noLabel` is a "{label}" template for guest pages that translate "No {label}". */
export function choiceLine(c: LineChoice, money: (n: number) => string, noLabel = "No {label}"): string {
  if (c.kind === "leave_out") return noLabel.replace("{label}", c.label.toLowerCase());
  const price = Number(c.price_delta);
  return price > 0 ? `${c.label} +${money(price)}` : c.label;
}
