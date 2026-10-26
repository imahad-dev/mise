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
}

export interface PaymentClaim {
  method: Method;
  reference: string | null;
  total: string;
  claimed_at: string;
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

/** The sentence a guest sees after choosing a method. */
export function claimMessage(claim: PaymentClaim, dict: TranslationDict, lang: string, currency: string): string {
  if (claim.method === "cash") return dict.pay.cash.replace("{total}", formatPrice(Number(claim.total), currency, lang));
  if (claim.method === "card") return dict.pay.card;
  return dict.pay.sent;
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

export const percent = (rate: string) => String(Number((Number(rate) * 100).toFixed(2)));
