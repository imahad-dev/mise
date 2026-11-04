import { formatPrice } from "ui";
import type { TranslationDict } from "../i18n";

/** Mirrors GuestBillDetail in services/api/src/schemas/payments.py. Decimals arrive as strings. */
export type Method = "cash" | "card" | "wallet" | "raast" | "bank_transfer";

export interface MethodPreview {
  method: Method;
  label: string;
  payment_class: "standard" | "digital";
  tax_rate: string;
  tax_amount: string;
  total: string;
  /** VAT is already in the prices (UK, Dubai): one total for every method. */
  tax_included: boolean;
}

export interface PaymentClaim {
  method: Method;
  reference: string | null;
  /** Includes the optional service when the guest chose it. */
  total: string;
  claimed_at: string;
  service_included: boolean;
}

export interface PaymentDetails {
  raast_id: string | null;
  jazzcash: string | null;
  easypaisa: string | null;
  iban: string | null;
  account_title: string | null;
  sample: boolean;
}

export interface GuestBill {
  bill_no: number | null;
  status: "open" | "settled" | "cancelled" | string;
  bill_requested_at: string | null;
  lines: { name: string; option_label: string | null; quantity: number; unit_price: string; line_total: string }[];
  subtotal: string;
  currency: string;
  methods: MethodPreview[];
  payment_details: PaymentDetails;
  claim: PaymentClaim | null;
  voided: { name: string; option_label: string | null; quantity: number }[];
  order_status: string | null;
  /** Set only on a settled bill. */
  payment_method: Method | null;
  tax_rate: string | null;
  total: string | null;
  /** The optional service charge; "0.0000" / "0.00" where none applies. */
  service_charge_rate: string;
  service_charge_amount: string;
  /** Counter pickup bills only: "K-042". */
  pickup_label?: string | null;
  /** Pay-it-forward chai on this bill once settled. */
  pay_forward_count?: number;
}

/** The API's 409 detail for a stale guest session (services/api/src/services/bills.py). */
export const VISIT_ENDED = "Your visit has ended — scan the table QR again";

export const needsReference = (method: string) => method === "wallet" || method === "raast" || method === "bank_transfer";

/** Same rule as REFERENCE in services/api/src/schemas/bills.py: ASCII only, 1-64 characters. */
export const isValidReference = (reference: string) => /^[A-Za-z0-9 _\-./#]{1,64}$/.test(reference.trim());

export type BillState = "none" | "open" | "claimed" | "paid" | "cancelled" | "ended";

/** What the order page says; the guest's own settled bill stays readable after the visit ends. */
export function billState(bill: GuestBill | null, ended: boolean): BillState {
  if (bill?.status === "settled") return "paid";
  if (bill?.status === "cancelled") return "cancelled";
  if (ended) return "ended";
  if (!bill) return "none";
  return bill.claim ? "claimed" : "open";
}

/** The sentence a guest sees after choosing a method; at the counter cash and card are paid there. */
export function claimMessage(claim: PaymentClaim, dict: TranslationDict, lang: string, currency: string, counter = false): string {
  const total = formatPrice(Number(claim.total), currency, lang);
  if (claim.method === "cash") return (counter ? dict.counter.cash : dict.pay.cash).replace("{total}", total);
  if (claim.method === "card") return counter ? dict.counter.card : dict.pay.card;
  return dict.pay.sent;
}

export type CounterState = "awaiting" | "preparing" | "ready" | "collected" | "cancelled";

/** Where a counter pickup order stands for the guest; null for table bills. A revived bill reads as open again. */
export function counterState(bill: GuestBill | null): CounterState | null {
  if (!bill?.pickup_label) return null;
  if (bill.status === "cancelled") return "cancelled";
  if (bill.status !== "settled") return "awaiting";
  if (bill.order_status === "collected") return "collected";
  return bill.order_status === "bumped" ? "ready" : "preparing";
}

/** The venue details a guest needs for this method, in display order; empty values are left out. */
export function detailsFor(method: Method, d: PaymentDetails): { key: keyof TranslationDict["pay"]["labels"]; value: string }[] {
  const keys = ({
    wallet: ["jazzcash", "easypaisa", "account_title"],
    raast: ["raast_id", "account_title"],
    bank_transfer: ["iban", "account_title"],
  } as const)[method as "wallet" | "raast" | "bank_transfer"] ?? [];
  return keys.flatMap((key) => (d[key] ? [{ key, value: d[key] as string }] : []));
}

/** The reference field after switching to a method: the claim's own reference for its method, else empty. */
export const referenceFor = (method: Method, claim: PaymentClaim | null) =>
  claim && claim.method === method ? (claim.reference ?? "") : "";

/** Copy to the clipboard; false (never a throw) when the browser has no clipboard or refuses. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator === "undefined" || !navigator.clipboard) return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** "Paid Rs 2,714 (incl. 16% sales tax) by Cash" for a settled bill, else null. */
export function paidText(bill: GuestBill, dict: TranslationDict, lang: string): string | null {
  if (bill.status !== "settled" || bill.total === null || bill.tax_rate === null || !bill.payment_method) return null;
  return dict.pay.paidAmount
    .replace("{total}", formatPrice(Number(bill.total), bill.currency, lang))
    .replace("{rate}", percent(bill.tax_rate))
    .replace("{method}", dict.pay.methods[bill.payment_method] ?? bill.payment_method);
}

/** The thank-you for pay-it-forward chai on a settled bill, else null. */
export function payForwardThanks(bill: GuestBill, dict: TranslationDict): string | null {
  const n = bill.pay_forward_count ?? 0;
  return bill.status === "settled" && n > 0 ? dict.bill.payForward.replace("{count}", String(n)) : null;
}

export const percent = (rate: string) => String(Number((Number(rate) * 100).toFixed(2)));

/** What the guest pays for a method: the method total plus the optional service when chosen. */
export const payTotal = (m: MethodPreview, serviceAmount: string, withService: boolean) =>
  Number(m.total) + (withService ? Number(serviceAmount) : 0);

/** "Add optional service (12.5%)" from the template and the rate as a fraction. */
export const serviceLine = (rate: string, template: string) => template.replace("{rate}", percent(rate));

/** The menu's tax line: VAT already in the price (UK, Dubai) or sales tax added to the bill. */
export const menuTaxNote = (pricesIncludeTax: boolean, dict: TranslationDict) =>
  pricesIncludeTax ? dict.menu.vatIncluded : dict.menu.taxNote;
