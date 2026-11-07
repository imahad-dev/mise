import { choiceLine, formatPrice, type LineChoice } from "ui";

/** Mirrors services/api/src/schemas/bills.py. Decimals arrive as strings. */
export interface BillLine {
  name: string;
  option_label: string | null;
  choices?: LineChoice[];
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface TaxPreview {
  payment_class: "standard" | "digital";
  tax_rate: string;
  tax_amount: string;
  total: string;
  /** VAT already inside the menu prices (UK, Dubai); the API always sends it. */
  tax_included?: boolean;
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
  /** Counter bills only (one order each); null/false on table bills. */
  pickup_label?: string | null;
  order_id?: string | null;
  /** awaiting_payment, placed, bumped, collected or cancelled */
  order_status?: string | null;
  collected_at?: string | null;
  pickup_yesterday?: boolean;
}

export interface BillDetail extends BillSummary {
  lines: BillLine[];
  preview_standard: TaxPreview | null;
  preview_digital: TaxPreview | null;
  payment_method: string | null;
  payment_reference: string | null;
  tax_jurisdiction: string | null;
  /** "on_top" or "included": set when the bill is settled. */
  tax_pricing: string | null;
  /** The optional service charge; "0.00" where none applies, the settled amount once settled. */
  service_charge_rate: string;
  service_charge_amount: string;
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
  /** The guest chose the optional service; their total includes it. The API always sends it. */
  service_included?: boolean;
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

/** Pakistani bills name the authorities they are not connected to; others keep only the first sentence. */
export const billFooter = (jurisdiction: string | null | undefined) =>
  // No jurisdiction: a bill from before venues outside Pakistan existed.
  !jurisdiction || jurisdiction === "PB" || jurisdiction === "ICT" ? SAMPLE_BILL_FOOTER : "Sample bill — not a tax invoice.";

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

/** "Guest said they paid by Raast QR (<total in the venue's currency>)": shown on bills cancelled after a claim. */
export const claimWarning = (claim: PaymentClaim, currency: string) =>
  `Guest said they paid by ${paymentLabel(claim.method)} (${formatPrice(Number(claim.total), currency)}) — any refund happens outside Mise.`;

/** Row chip for an open bill's claim: "Guest paying: Raast QR · ref TX4471…", "Guest paying: cash", "Card machine requested". */
export function claimChip(claim: PaymentClaim): string {
  if (claim.method === "card") return "Card machine requested";
  if (claim.method === "cash") return "Guest paying: cash";
  return `Guest paying: ${claimSummary(claim, 8)}`;
}

/** "Raast QR · ref RAAST4471": the full reference unless maxRef cuts it (list chips only). */
export function claimSummary(claim: PaymentClaim, maxRef = Infinity): string {
  const ref = claim.reference ?? "";
  return `${paymentLabel(claim.method)}${ref ? ` · ref ${ref.length > maxRef ? `${ref.slice(0, maxRef)}…` : ref}` : ""}`;
}

/** amount_due_after_claim as words: positive is still due, negative overpaid, zero nothing. */
export function amountDueText(due: string | null, currency: string): string | null {
  const n = Number(due ?? 0);
  if (!n) return null;
  return `${formatPrice(Math.abs(n), currency)} ${n > 0 ? "still due" : "overpaid"}`;
}

/**
 * The settle body. expected_total comes from the server's preview for the selected method plus
 * the server's optional service amount when included, never from the claim; null when that
 * method has no preview (no tax rate).
 */
export function settlePayload(
  bill: Pick<BillDetail, "methods"> & Partial<Pick<BillDetail, "service_charge_amount">>,
  method: PaymentMethod,
  reference: string,
  acknowledgeReused: boolean,
  serviceIncluded = false,
  acknowledgeServiceChange = false,
) {
  const preview = previewFor(bill, method);
  if (!preview) return null;
  const ref = method === "cash" ? "" : reference.trim();
  const service = serviceIncluded ? Number(bill.service_charge_amount ?? 0) : 0;
  return {
    payment_method: method,
    payment_reference: ref || null,
    expected_total: (Number(preview.total) + service).toFixed(2),
    expected_method: method,
    acknowledge_reused_reference: acknowledgeReused,
    service_included: service > 0,
    acknowledge_service_change: acknowledgeServiceChange,
  };
}

/**
 * Staff's service choice differs from the guest's claim on a bill with a service charge: settle
 * then needs acknowledge_service_change. The key changes with the bill, claim and choice, so an
 * acknowledgement never outlives what it confirmed; null when nothing needs confirming.
 */
export const serviceChangeKey = (
  d: (Pick<BillDetail, "id" | "claim"> & Partial<Pick<BillDetail, "service_charge_amount">>) | null,
  serviceOn: boolean,
) => {
  const claimed = d?.claim?.service_included ?? false;
  return d?.claim && Number(d.service_charge_amount ?? 0) > 0 && claimed !== serviceOn ? `${d.id}|${d.claim.claimed_at}|${claimed}|${serviceOn}` : null;
};

/** Changes whenever the reused-reference warnings could change: an acknowledgement never outlives it. */
export const warningKey = (d: Pick<BillDetail, "reused_reference_bill_no" | "reused_reference_open_bill_no" | "claim"> | null) =>
  d ? `${d.reused_reference_bill_no ?? ""}|${d.reused_reference_open_bill_no ?? ""}|${d.claim?.reference ?? ""}` : "";

const sameClaim = (a: PaymentClaim | null, b: PaymentClaim | null) =>
  (a?.method ?? null) === (b?.method ?? null) &&
  (a?.reference ?? null) === (b?.reference ?? null) &&
  (a?.service_included ?? false) === (b?.service_included ?? false);

/**
 * A live refresh brought a claim: follow it while staff haven't edited method or reference,
 * otherwise keep their choice and tell them.
 */
export function nextFormState(
  prev: PaymentClaim | null,
  next: PaymentClaim | null,
  touched: boolean,
): { apply: { method: PaymentMethod; reference: string; serviceIncluded: boolean } | null; notice: string | null } {
  if (!next || sameClaim(prev, next)) return { apply: null, notice: null };
  if (touched) {
    const paymentChanged = (prev?.method ?? null) !== next.method || (prev?.reference ?? null) !== (next.reference ?? null);
    const serviceChanged = (prev?.service_included ?? false) !== (next.service_included ?? false);
    const service = `turned the optional service ${next.service_included ? "on" : "off"}`;
    const what = paymentChanged ? `changed their payment to ${claimSummary(next)}${serviceChanged ? ` and ${service}` : ""}` : service;
    return { apply: null, notice: `The guest ${what} — check before confirming` };
  }
  const method = PAYMENT_METHODS.find((m) => m.value === next.method)?.value ?? "cash";
  return { apply: { method, reference: next.reference ?? "", serviceIncluded: next.service_included ?? false }, notice: null };
}

export const VOID_REASONS = ["Wrong table", "Guest changed mind", "Duplicate", "Other"] as const;

/** The reason sent with a void: the picked one, or the typed text for Other (1-200 characters). */
export function voidReason(choice: (typeof VOID_REASONS)[number], other: string): string | null {
  if (choice !== "Other") return choice;
  const text = other.trim();
  return text && text.length <= 200 ? text : null;
}

type CounterRow = Pick<BillSummary, "status" | "pickup_label" | "order_status" | "collected_at" | "pickup_yesterday">;

export type CounterColumn = "awaiting" | "preparing" | "ready";

/** Where a counter bill sits in the queue: unpaid, paid and cooking, bumped; null once collected or cancelled. */
export function counterColumn(row: CounterRow): CounterColumn | null {
  if (!row.pickup_label) return null; // table bills never join the counter queue
  if (row.status === "open") return "awaiting";
  if (row.status !== "settled" || row.collected_at || row.order_status === "collected") return null;
  if (row.order_status === "placed") return "preparing";
  return row.order_status === "bumped" ? "ready" : null;
}

/** "K-042", or "K-042 · Yesterday" for an order numbered on an earlier local day. */
export const pickupText = (row: CounterRow) => `${row.pickup_label ?? "—"}${row.pickup_yesterday ? " · Yesterday" : ""}`;

/** services/api/src/services/bills.py EXPIRED. */
export const EXPIRED_UNPAID = "Expired unpaid";

/** Cancelled by the 30-minute expiry, not by staff: money may still arrive, and settling revives it. */
export const isExpiredUnpaid = (b: Pick<BillSummary, "status" | "cancel_reason" | "pickup_label"> & { cancelled_by_name?: string | null }) =>
  b.status === "cancelled" && b.cancel_reason === EXPIRED_UNPAID && Boolean(b.pickup_label) && !b.cancelled_by_name;

/** Collected can be undone for 60 s (server clock). */
export const UNDO_MS = 60_000;
export const undoSecondsLeft = (startedAt: number, now: number) => Math.max(0, Math.ceil((startedAt + UNDO_MS - now) / 1000));

/**
 * Seconds of undo left on a "Just collected" queue row, 0 when it is not one.
 * shortcut: counts collected_at (server clock) on the device clock, so a skewed device shows a shifted countdown; the server still decides.
 */
export const collectedUndoLeft = (row: Pick<BillSummary, "pickup_label" | "collected_at">, now: number) =>
  row.pickup_label && row.collected_at ? undoSecondsLeft(Date.parse(row.collected_at), now) : 0;

export const SETTINGS_PAYMENT_FIELDS = ["raast_id", "jazzcash", "easypaisa", "iban", "account_title"] as const;

/** "0.0750" -> 7.5 */
export const ratePercent = (rate: string) => Number((Number(rate) * 100).toFixed(2));

/** The service-charge field (a percentage) as the API's fraction: "12.5" -> "0.1250"; blank is 0 (off); null unless 0-20 in 0.5 steps. */
export function serviceRateFraction(percent: string): string | null {
  const n = Number(percent.trim() || 0);
  return Number.isFinite(n) && n >= 0 && n <= 20 && Number.isInteger(n * 2) ? (n / 100).toFixed(4) : null;
}

/**
 * The PATCH /settings body: every field, always; empty text clears (null); a checkbox is "on" or "".
 * The service-charge rate goes only where the venue may offer one.
 */
export function settingsBody(form: Record<string, string | undefined>, sample: boolean, serviceAllowed = false) {
  const value = (key: string) => form[key]?.trim() || null;
  return {
    payment_details: { ...Object.fromEntries(SETTINGS_PAYMENT_FIELDS.map((k) => [k, value(k)])), sample },
    pickup_prefix: value("pickup_prefix"),
    service_extra_label: value("service_extra_label"),
    sitting_code_required: form.sitting_code_required === "on",
    ...(serviceAllowed ? { service_charge_rate: serviceRateFraction(form.service_charge_rate ?? "") } : {}),
  };
}

/** Mirrors TaxRule in services/api/src/schemas/owner.py. */
export interface TaxRule {
  name: string;
  rate: string;
  pricing: "on_top" | "included";
}

/** The settings page's read-only tax line; null when the venue has no tax rule. */
export function taxRuleText(rule: TaxRule | null): string | null {
  if (!rule) return null;
  return rule.pricing === "included"
    ? `Prices include VAT ${ratePercent(rule.rate)}% (${rule.name})`
    : `Sales tax added to bills (${rule.name})`;
}

/** PATCH /settings errors by field: {field, message} for payment details, FastAPI's list, the 409 prefix message or the 422 service-charge message. */
export function settingsErrors(status: number, body: unknown): Record<string, string> {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (status === 409) return { pickup_prefix: typeof detail === "string" ? detail : "Finish open counter orders first" };
  // The only plain-text 422 from PATCH /settings refuses the service charge.
  if (status === 422 && typeof detail === "string") return { service_charge_rate: detail };
  if (Array.isArray(detail)) {
    const out: Record<string, string> = {};
    for (const d of detail as { loc?: unknown[]; msg?: string }[]) {
      const field = String(d.loc?.[1] ?? "form");
      out[field] ??= d.msg ?? "Invalid value";
    }
    return out;
  }
  if (detail && typeof detail === "object" && "field" in detail) {
    const d = detail as { field: unknown; message?: unknown };
    return { [String(d.field)]: String(d.message ?? "Invalid value") };
  }
  return { form: typeof detail === "string" ? detail : `Request failed (${status})` };
}

export const billNo = (n: number | null) => (n === null ? "Bill no. —" : `Bill no. ${String(n).padStart(4, "0")}`);

const TAX_CLASS: Record<string, string> = { cash: "cash", bank_transfer: "bank transfer" };

export function taxLabel(rate: string, method: string | null, included = false): string {
  if (included) return `VAT ${ratePercent(rate)}% included`;
  return `Sales tax (illustrative) ${ratePercent(rate)}% — ${TAX_CLASS[method ?? ""] ?? "card, wallet or QR"}`;
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
> &
  Partial<Pick<BillDetail, "tax_jurisdiction" | "tax_pricing" | "service_charge_amount">>;

export interface BillRow {
  label: string;
  amount: string;
}

type TotalsBill = Pick<
  SampleBill,
  "currency" | "subtotal" | "tax_rate" | "tax_amount" | "total" | "payment_method" | "tax_pricing" | "service_charge_amount"
>;

/** Subtotal, tax, the optional service when taken, and total; a VAT-included bill says the VAT is inside. */
export function totalRows(bill: TotalsBill): BillRow[] {
  const money = (v: string | null | undefined) => formatPrice(Number(v ?? 0), bill.currency);
  return [
    { label: "Subtotal", amount: money(bill.subtotal) },
    { label: taxLabel(bill.tax_rate ?? "0", bill.payment_method, bill.tax_pricing === "included"), amount: money(bill.tax_amount) },
    ...(Number(bill.service_charge_amount ?? 0) > 0 ? [{ label: "Optional service", amount: money(bill.service_charge_amount) }] : []),
    { label: "Total", amount: money(bill.total) },
  ];
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
      label: [`${l.quantity} × ${l.name}${l.option_label ? ` — ${l.option_label}` : ""}`, ...(l.choices ?? []).map((c) => choiceLine(c, (n) => formatPrice(n, bill.currency)))].join(" · "),
      amount: money(l.line_total),
    })),
    totals: totalRows(bill),
    payment: `Paid by ${paymentLabel(bill.payment_method)}`,
    footer: billFooter(bill.tax_jurisdiction),
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
