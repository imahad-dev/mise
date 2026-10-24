import { formatPrice } from "ui";

/** Mirrors services/api/src/schemas/bills.py. Decimals arrive as strings. */
export interface BillLine {
  name: string;
  option_label: string | null;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface TaxPreview {
  payment_class: "standard" | "digital";
  tax_rate: string;
  tax_amount: string;
  total: string;
}

export interface BillSummary {
  id: string;
  bill_no: number | null;
  table_label: string | null;
  status: string;
  opened_at: string;
  order_count: number;
  subtotal: string;
  bill_requested_at: string | null;
}

export interface BillDetail extends BillSummary {
  lines: BillLine[];
  preview_standard: TaxPreview | null;
  preview_digital: TaxPreview | null;
  payment_method: string | null;
  payment_reference: string | null;
  tax_jurisdiction: string | null;
  tax_rate: string | null;
  tax_amount: string | null;
  total: string | null;
  settled_at: string | null;
  restaurant_name: string;
  restaurant_city: string | null;
  restaurant_timezone: string;
  currency: string;
}

export const SAMPLE_BILL_FOOTER =
  "Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority.";

export const PAYMENT_METHODS = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "wallet", label: "JazzCash / Easypaisa" },
  { value: "raast", label: "Raast QR" },
  { value: "bank_transfer", label: "Bank transfer" },
] as const;

export type PaymentMethod = (typeof PAYMENT_METHODS)[number]["value"];

export const paymentLabel = (method: string | null) =>
  PAYMENT_METHODS.find((m) => m.value === method)?.label ?? method ?? "";

export const billNo = (n: number | null) => (n === null ? "Bill no. —" : `Bill no. ${String(n).padStart(4, "0")}`);

const TAX_CLASS: Record<string, string> = { cash: "cash", bank_transfer: "bank transfer" };

export function taxLabel(rate: string, method: string | null): string {
  const pct = Number((Number(rate) * 100).toFixed(2));
  return `Sales tax (illustrative) ${pct}% — ${TAX_CLASS[method ?? ""] ?? "card, wallet or QR"}`;
}

export const localDateTime = (iso: string, timeZone: string) =>
  new Intl.DateTimeFormat("en-PK", { timeZone, dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));

type SampleBill = Pick<
  BillDetail,
  | "restaurant_name"
  | "restaurant_city"
  | "restaurant_timezone"
  | "currency"
  | "bill_no"
  | "table_label"
  | "settled_at"
  | "lines"
  | "subtotal"
  | "tax_rate"
  | "tax_amount"
  | "total"
  | "payment_method"
>;

export interface BillRow {
  label: string;
  amount: string;
}

/** The pieces of a settled sample bill; the print page renders these, sampleBillText joins them. */
export function sampleBillPieces(bill: SampleBill) {
  const money = (v: string | null) => formatPrice(Number(v ?? 0), bill.currency);
  return {
    header: [
      bill.restaurant_name,
      ...(bill.restaurant_city ? [bill.restaurant_city] : []),
      billNo(bill.bill_no),
      ...(bill.settled_at ? [localDateTime(bill.settled_at, bill.restaurant_timezone)] : []),
      ...(bill.table_label ? [`Table ${bill.table_label}`] : []),
    ],
    lines: bill.lines.map<BillRow>((l) => ({
      label: `${l.quantity} × ${l.name}${l.option_label ? ` — ${l.option_label}` : ""}`,
      amount: money(l.line_total),
    })),
    totals: [
      { label: "Subtotal", amount: money(bill.subtotal) },
      { label: taxLabel(bill.tax_rate ?? "0", bill.payment_method), amount: money(bill.tax_amount) },
      { label: "Total", amount: money(bill.total) },
    ] as BillRow[],
    payment: `Paid by ${paymentLabel(bill.payment_method)}`,
    footer: SAMPLE_BILL_FOOTER,
  };
}

export function sampleBillText(bill: SampleBill): string {
  const p = sampleBillPieces(bill);
  const row = (r: BillRow) => `${r.label}  ${r.amount}`;
  return [...p.header, "", ...p.lines.map(row), "", ...p.totals.map(row), p.payment, "", p.footer].join("\n");
}

/** FastAPI error body → one readable line. */
export async function apiError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
  } catch {
    // not JSON
  }
  return `Request failed (${res.status})`;
}
