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

export interface MethodPreview extends TaxPreview {
  method: string;
  label: string;
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
  claim: PaymentClaim | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
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
  methods: MethodPreview[];
  claim: PaymentClaim | null;
  amount_due_after_claim: string | null;
  reused_reference_bill_no: number | null;
  reused_reference_open_bill_no: number | null;
  orders: BillOrder[];
  settled_by_name: string | null;
  cancelled_by_name: string | null;
}

export interface PaymentClaim {
  method: string;
  reference: string | null;
  total: string;
  claimed_at: string;
}

export interface BillOrder {
  order_id: string;
  placed_at: string;
  status: string;
  device_label: string;
  joined_late: boolean;
  voided: boolean;
  void_reason: string | null;
  lines: BillLine[];
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

/** The server's preview for this method; settle sends its total back as expected_total. */
export const previewFor = (bill: Pick<BillDetail, "methods">, method: string) =>
  bill.methods.find((m) => m.method === method) ?? null;

export const paymentLabel = (method: string | null) =>
  PAYMENT_METHODS.find((m) => m.value === method)?.label ?? method ?? "";

/** "Guest said they paid by Raast QR (Rs 2,527.00)": shown on bills cancelled after a claim. */
export const claimWarning = (claim: PaymentClaim, currency: string) =>
  `Guest said they paid by ${paymentLabel(claim.method)} (${formatPrice(Number(claim.total), currency)}) — any refund happens outside Mise.`;

/** Row chip for an open bill's claim: "Guest paying: Raast QR · ref TX4471…", "Guest paying: cash", "Card machine requested". */
export function claimChip(claim: PaymentClaim): string {
  if (claim.method === "card") return "Card machine requested";
  if (claim.method === "cash") return "Guest paying: cash";
  const ref = claim.reference ?? "";
  return `Guest paying: ${paymentLabel(claim.method)}${ref ? ` · ref ${ref.length > 8 ? `${ref.slice(0, 8)}…` : ref}` : ""}`;
}

/** amount_due_after_claim as words: positive is still due, negative overpaid, zero nothing. */
export function amountDueText(due: string | null, currency: string): string | null {
  const n = Number(due ?? 0);
  if (!n) return null;
  return `${formatPrice(Math.abs(n), currency)} ${n > 0 ? "still due" : "overpaid"}`;
}

/**
 * The settle body. expected_total comes from the server's preview for the selected method,
 * never from the claim; null when that method has no preview (no tax rate).
 */
export function settlePayload(bill: Pick<BillDetail, "methods">, method: PaymentMethod, reference: string, acknowledgeReused: boolean) {
  const preview = previewFor(bill, method);
  if (!preview) return null;
  const ref = method === "cash" ? "" : reference.trim();
  return {
    payment_method: method,
    payment_reference: ref || null,
    expected_total: preview.total,
    expected_method: method,
    acknowledge_reused_reference: acknowledgeReused,
  };
}

/** Changes whenever the reused-reference warnings could change: an acknowledgement never outlives it. */
export const warningKey = (d: Pick<BillDetail, "reused_reference_bill_no" | "reused_reference_open_bill_no" | "claim"> | null) =>
  d ? `${d.reused_reference_bill_no ?? ""}|${d.reused_reference_open_bill_no ?? ""}|${d.claim?.reference ?? ""}` : "";

const sameClaim = (a: PaymentClaim | null, b: PaymentClaim | null) =>
  (a?.method ?? null) === (b?.method ?? null) && (a?.reference ?? null) === (b?.reference ?? null);

/**
 * A live refresh brought a claim: follow it while staff haven't edited method or reference,
 * otherwise keep their choice and tell them.
 */
export function nextFormState(
  prev: PaymentClaim | null,
  next: PaymentClaim | null,
  touched: boolean,
): { apply: { method: PaymentMethod; reference: string } | null; notice: string | null } {
  if (!next || sameClaim(prev, next)) return { apply: null, notice: null };
  if (touched) return { apply: null, notice: `The guest changed their payment to ${claimChip(next)} — check before confirming` };
  const method = PAYMENT_METHODS.find((m) => m.value === next.method)?.value ?? "cash";
  return { apply: { method, reference: next.reference ?? "" }, notice: null };
}

export const VOID_REASONS = ["Wrong table", "Guest changed mind", "Duplicate", "Other"] as const;

/** The reason sent with a void: the picked one, or the typed text for Other (1-200 characters). */
export function voidReason(choice: (typeof VOID_REASONS)[number], other: string): string | null {
  if (choice !== "Other") return choice;
  const text = other.trim();
  return text && text.length <= 200 ? text : null;
}

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
