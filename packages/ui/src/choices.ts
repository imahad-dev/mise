export interface LineChoice {
  choice_id?: string;
  group?: string;
  kind: "pick" | "add" | "leave_out";
  label: string;
  price_delta: string | number;
}

/** "Onions" -> "onions", "BBQ sauce" stays: lowercase the first letter only when the second is lowercase. */
const lowerFirst = (s: string) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);

/** `noLabel` is a "{label}" template for guest pages that translate "No {label}". */
export function choiceLine(c: LineChoice, money: (n: number) => string, noLabel = "No {label}"): string {
  if (c.kind === "leave_out") return noLabel.replace("{label}", lowerFirst(c.label));
  const price = Number(c.price_delta);
  return price > 0 ? `${c.label} +${money(price)}` : c.label;
}
