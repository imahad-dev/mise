"use client";

import React, { useEffect, useState } from "react";
import { Button, Sheet, formatPrice } from "ui";
import { getDictionary } from "../i18n";
import {
  claimMessage,
  copyText,
  detailsFor,
  isValidReference,
  needsReference,
  payTotal,
  percent,
  referenceFor,
  serviceLine,
  type GuestBill,
  type Method,
} from "../lib/pay";

export interface PaySheetProps {
  lang: string;
  bill: GuestBill;
  /** The order page's order: the claim goes to that order's bill only. */
  orderId?: string;
  open: boolean;
  onClose: () => void;
  /** The server's answer to a claim. */
  onUpdated: (bill: GuestBill) => void;
  /** 409: the bill is no longer open or the visit has ended; detail is the API's message. */
  onConflict: (detail: string | null) => void;
}

/** Lines, per-method totals and the guest's payment claim. Never settles: staff confirm. */
export function PaySheet({ lang, bill, orderId, open, onClose, onUpdated, onConflict }: PaySheetProps) {
  const dict = getDictionary(lang);
  const money = (v: string) => formatPrice(Number(v), bill.currency, lang);
  const [selected, setSelected] = useState<Method | null>(bill.claim?.method ?? null);
  const [reference, setReference] = useState(bill.claim?.reference ?? "");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<{ key: string; ok: boolean } | null>(null);
  // The optional service starts on; one tap turns it off.
  const [withService, setWithService] = useState(bill.claim?.service_included ?? true);

  // A claim made on another phone at the table becomes this sheet's starting point.
  useEffect(() => {
    if (!open) return;
    setSelected(bill.claim?.method ?? null);
    setReference(bill.claim?.reference ?? "");
    setWithService(bill.claim?.service_included ?? true);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the sheet opens
  }, [open]);

  const isOpen = bill.status === "open";
  const hasService = Number(bill.service_charge_amount) > 0;
  const addService = hasService && withService;
  const included = bill.methods[0]?.tax_included ?? false;

  const claim = async (method: Method, ref: string | null, service: boolean) => {
    setPosting(true);
    setError(null);
    try {
      const r = await fetch(`/api/guest/bill/payment${orderId ? `?order_id=${encodeURIComponent(orderId)}` : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method, reference: ref, service_included: hasService && service }),
      });
      if (r.ok) {
        onUpdated((await r.json()) as GuestBill);
      } else if (r.status === 409) {
        const body = (await r.json().catch(() => null)) as { detail?: unknown } | null;
        onConflict(typeof body?.detail === "string" ? body.detail : null);
      } else if (r.status === 422) {
        setError(needsReference(method) ? dict.pay.invalidReference : dict.pay.networkError);
      } else {
        setError(dict.pay.networkError);
      }
    } catch {
      setError(dict.pay.networkError); // the typed reference stays; the server is idempotent
    } finally {
      setPosting(false);
    }
  };

  const choose = (method: Method) => {
    if (method !== selected) {
      setCopied(null);
      setReference(referenceFor(method, bill.claim));
    }
    setSelected(method);
    setError(null);
    if (!needsReference(method)) void claim(method, null, withService);
  };

  const sendReference = () => {
    if (!selected) return;
    if (!isValidReference(reference)) {
      setError(dict.pay.invalidReference);
      return;
    }
    void claim(selected, reference.trim(), withService);
  };

  const copy = async (key: string, value: string) => setCopied({ key, ok: await copyText(value) });

  // A cash or card claim follows the switch at once; a transfer needs the guest to send it again.
  const toggleService = () => {
    const next = !withService;
    setWithService(next);
    if (bill.claim && !needsReference(bill.claim.method)) void claim(bill.claim.method, null, next);
  };
  const staleClaim = hasService && bill.claim !== null && needsReference(bill.claim.method) && bill.claim.service_included !== withService;
  const toPay = (m: (typeof bill.methods)[number]) => money(String(payTotal(m, bill.service_charge_amount, addService)));
  const preview = bill.methods.find((m) => m.method === selected) ?? null;
  const details = selected ? detailsFor(selected, bill.payment_details) : [];

  return (
    <Sheet open={open} onClose={onClose} title={bill.pickup_label ? dict.counter.payPrompt : dict.pay.button}>
      <ul className="divide-y divide-line text-sm">
        {bill.lines.map((l, i) => (
          <li key={i} className="flex justify-between gap-3 py-2">
            <span className="text-ink">
              {l.quantity} × {l.name}
              {l.option_label && <span className="text-ink-muted"> — {l.option_label}</span>}
            </span>
            <span className="text-ink-muted">{money(l.line_total)}</span>
          </li>
        ))}
      </ul>
      {bill.voided.map((v, i) => (
        <p key={i} className="text-sm text-danger-fg">
          {dict.pay.removed.replace("{name}", v.option_label ? `${v.name} — ${v.option_label}` : v.name).replace("{qty}", String(v.quantity))}
        </p>
      ))}
      <p className="flex justify-between text-sm font-semibold text-ink">
        <span>{dict.pay.subtotal}</span>
        <span>{money(bill.subtotal)}</span>
      </p>

      {isOpen && hasService && (
        <button
          type="button"
          role="switch"
          aria-checked={withService}
          disabled={posting}
          onClick={toggleService}
          className="flex min-h-12 w-full items-center justify-between gap-3 rounded-xl border border-line bg-card px-4 py-3 text-left text-sm text-ink"
        >
          <span>{serviceLine(bill.service_charge_rate, dict.pay.service, lang).replace("{amount}", money(bill.service_charge_amount))}</span>
          <span aria-hidden className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${withService ? "bg-terracotta" : "bg-line"}`}>
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-paper shadow transition-all ${withService ? "left-[22px]" : "left-0.5"}`} />
          </span>
        </button>
      )}

      {isOpen && included && (
        <div className="space-y-1">
          <p className="flex justify-between text-base font-semibold text-ink">
            <span>{dict.pay.total}</span>
            <span data-testid="pay-total">{toPay(bill.methods[0])}</span>
          </p>
          <p className="text-xs text-ink-muted">
            {dict.pay.vatIncluded.replace("{rate}", percent(bill.methods[0].tax_rate, lang)).replace("{amount}", money(bill.methods[0].tax_amount))}
          </p>
        </div>
      )}

      {isOpen && (
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-semibold text-ink">{dict.pay.choose}</legend>
          {bill.methods.map((m) => (
            <button
              key={m.method}
              type="button"
              aria-pressed={selected === m.method}
              disabled={posting}
              onClick={() => choose(m.method)}
              className={`flex w-full items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left ${
                selected === m.method ? "border-terracotta bg-paper-2" : "border-line bg-card"
              }`}
            >
              <span>
                <span className="block font-semibold text-ink">{dict.pay.methods[m.method] ?? m.label}</span>
                {!included && <span className="block text-xs text-ink-muted">{dict.pay.taxRate.replace("{rate}", percent(m.tax_rate, lang))}</span>}
              </span>
              {!included && <span className="font-semibold text-ink">{toPay(m)}</span>}
            </button>
          ))}
        </fieldset>
      )}

      {isOpen && selected && needsReference(selected) && preview && (
        <div className="space-y-3">
          <div
            className={`space-y-2 rounded-xl border p-3 text-sm ${
              bill.payment_details.sample ? "border-warn-fg bg-warn-bg" : "border-line bg-card"
            }`}
          >
            {bill.payment_details.sample && <p className="font-semibold text-warn-fg">{dict.pay.sampleBanner}</p>}
            <p className="text-ink">{dict.pay.payTo.replace("{total}", toPay(preview))}</p>
            {details.map((d) => (
              <div key={d.key} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  <span className="block text-xs text-ink-muted">{dict.pay.labels[d.key]}</span>
                  <span className="block select-all font-mono text-ink">{d.value}</span>
                </span>
                <span className="flex items-center gap-2">
                  {copied?.key === d.key && (
                    <span role="status" className="text-xs text-ink-muted">
                      {copied.ok ? dict.pay.copied : dict.pay.copyFailed}
                    </span>
                  )}
                  <Button variant="outline" aria-label={`${dict.pay.copy} ${dict.pay.labels[d.key]}`} onClick={() => void copy(d.key, d.value)}>
                    {dict.pay.copy}
                  </Button>
                </span>
              </div>
            ))}
          </div>
          <label className="block space-y-1 text-sm text-ink">
            <span>{dict.pay.reference}</span>
            <input
              type="text"
              value={reference}
              maxLength={64}
              autoComplete="off"
              onChange={(e) => setReference(e.target.value)}
              className="w-full rounded-lg border border-line bg-paper px-3 py-2 focus:border-terracotta focus:outline-none focus:ring-1 focus:ring-terracotta"
            />
          </label>
          <Button className="w-full" disabled={posting} onClick={sendReference}>
            {posting ? dict.pay.sending : dict.pay.paid}
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger-fg">
          {error}
        </p>
      )}
      <p role="status" className="text-sm font-semibold text-ink">
        {/* The table's latest claim, from any phone: polling keeps it current. */}
        {!isOpen || !bill.claim || posting
          ? ""
          : staleClaim
            ? dict.pay.serviceChanged.replace("{button}", dict.pay.paid)
            : claimMessage(bill.claim, dict, lang, bill.currency, Boolean(bill.pickup_label))}
      </p>
    </Sheet>
  );
}
