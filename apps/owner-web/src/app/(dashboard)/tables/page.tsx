"use client";

import React, { useEffect, useState } from "react";
import { Badge, Button, Card } from "ui";
import { useVenue } from "../../../lib/venue";
import { settingsErrors } from "../../../lib/bill";
import QRCode from "qrcode";

interface TableItem {
  id: string;
  restaurant_id: string;
  label: string;
  qr_token: string;
  guest_url: string;
  /** "counter" for the counter / pickup QR. */
  kind: string;
  qrDataUrl?: string;
}

/** Mirrors SettingsResponse in services/api/src/schemas/owner.py. */
interface VenueSettingsBody {
  payment_details: Partial<Record<PaymentField, string>> & { sample?: boolean };
  service_extra_label: string | null;
  pickup_prefix: string | null;
}

const PAYMENT_FIELDS = [
  { key: "raast_id", label: "Raast ID", hint: "Mobile number or IBAN" },
  { key: "jazzcash", label: "JazzCash", hint: "03XXXXXXXXX" },
  { key: "easypaisa", label: "Easypaisa", hint: "03XXXXXXXXX" },
  { key: "iban", label: "IBAN", hint: "PK.. (24 characters)" },
  { key: "account_title", label: "Account title", hint: "Required with any of the above" },
] as const;
type PaymentField = (typeof PAYMENT_FIELDS)[number]["key"];
const INPUT =
  "w-full rounded-lg border border-line bg-paper px-3 py-2 focus:border-terracotta focus:outline-none focus:ring-1 focus:ring-terracotta";

/** Payment details guests pay into, the pickup prefix and the extra call reason (owner only). */
function VenueSettings({ slug }: { slug: string }) {
  const [loaded, setLoaded] = useState<VenueSettingsBody | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const apply = (body: VenueSettingsBody) => {
    setLoaded(body);
    setForm({
      ...Object.fromEntries(PAYMENT_FIELDS.map((f) => [f.key, body.payment_details[f.key] ?? ""])),
      pickup_prefix: body.pickup_prefix ?? "",
      service_extra_label: body.service_extra_label ?? "",
    });
  };

  useEffect(() => {
    let cancelled = false;
    setLoaded(null);
    fetch(`/api/restaurants/${slug}/settings`)
      .then(async (r) => {
        if (r.ok && !cancelled) apply((await r.json()) as VenueSettingsBody);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (!loaded) return null;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    setSaved(false);
    const extra = form.service_extra_label.trim();
    try {
      const res = await fetch(`/api/restaurants/${slug}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payment_details: {
            ...Object.fromEntries(PAYMENT_FIELDS.map((f) => [f.key, form[f.key].trim() || null])),
            sample: loaded.payment_details.sample === true,
          },
          pickup_prefix: form.pickup_prefix.trim() || null,
          // The API keeps the current label when this is left out; it cannot be cleared.
          ...(extra ? { service_extra_label: extra } : {}),
        }),
      });
      if (res.ok) {
        apply((await res.json()) as VenueSettingsBody);
        setSaved(true);
      } else {
        setErrors(settingsErrors(res.status, await res.json().catch(() => null)));
      }
    } catch {
      setErrors({ form: "Network error. Try again." });
    } finally {
      setBusy(false);
    }
  };

  const field = (key: string, label: string, hint: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label key={key} className="block space-y-1 text-sm text-ink">
      <span className="font-semibold">{label}</span>
      <input
        type="text"
        value={form[key] ?? ""}
        onChange={(e) => {
          setForm({ ...form, [key]: key === "pickup_prefix" ? e.target.value.toUpperCase() : e.target.value });
          setSaved(false);
        }}
        aria-invalid={Boolean(errors[key])}
        aria-describedby={errors[key] ? `${key}-error` : undefined}
        className={INPUT}
        {...extra}
      />
      <span className="block text-xs text-ink-muted">{hint}</span>
      {errors[key] && (
        <span id={`${key}-error`} className="block text-xs font-semibold text-danger-fg">
          {errors[key]}
        </span>
      )}
    </label>
  );
  const known = new Set<string>([...PAYMENT_FIELDS.map((f) => f.key), "pickup_prefix", "service_extra_label"]);
  const other = Object.entries(errors).filter(([k]) => !known.has(k));

  return (
    <Card className="space-y-4 print:hidden">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-ink">Payments and counter</h2>
        {loaded.payment_details.sample && <Badge>Sample — demo only</Badge>}
      </div>
      <form onSubmit={save} className="space-y-4" noValidate>
        <fieldset className="grid gap-3 sm:grid-cols-2">
          <legend className="mb-2 text-sm text-ink-muted">Where guests send money. Leave a method empty to hide it.</legend>
          {PAYMENT_FIELDS.map((f) => field(f.key, f.label, f.hint, { maxLength: 80 }))}
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">
          {field("pickup_prefix", "Pickup prefix", "1–3 capital letters, e.g. K for K-042. Empty uses K.", { maxLength: 3 })}
          {field("service_extra_label", "Extra call reason", "Shown on Call waiter, e.g. Extra naan", { maxLength: 40 })}
        </div>
        {other.map(([k, message]) => (
          <p key={k} role="alert" className="text-sm text-danger-fg">
            {k === "form" ? message : `${k}: ${message}`}
          </p>
        ))}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save settings"}
          </Button>
          {saved && (
            <span role="status" className="text-sm text-ink">
              Saved
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}

export default function TablesPage() {
  const { venue } = useVenue();
  const slug = venue?.slug;
  const [tables, setTables] = useState<TableItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setTables([]);
    setError(null);
    setLoading(true);
    let cancelled = false;
    async function loadTables() {
      try {
        const res = await fetch(`/api/restaurants/${slug}/tables`);
        if (!res.ok) {
          throw new Error(`Failed to load tables (${res.status})`);
        }
        const data: TableItem[] = await res.json();

        // Generate QR codes using qrcode package
        const withQr = await Promise.all(
          data.map(async (table) => {
            try {
              const qrDataUrl = await QRCode.toDataURL(table.guest_url, {
                width: 320,
                margin: 2,
                color: {
                  dark: "#000000",
                  light: "#ffffff",
                },
              });
              return { ...table, qrDataUrl };
            } catch {
              return table;
            }
          })
        );

        // The counter QR first; tables keep the server's label order.
        if (!cancelled) setTables(withQr.sort((a, b) => Number(b.kind === "counter") - Number(a.kind === "counter")));
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadTables();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const handlePrint = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="py-20 text-center">
        <div className="inline-block w-8 h-8 border-2 border-terracotta border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-ink-muted mt-2">Loading tables & generating QR codes...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-danger-bg border border-danger-fg/40 rounded-2xl text-xs text-danger-fg">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line pb-4 print:hidden">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">
            Dining Tables & <span className="text-terracotta">QR Cards</span>
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Printable guest QR codes with direct onboarding URLs.
          </p>
        </div>
        <button
          onClick={handlePrint}
          className="btn-primary"
        >
          <span>🖨️</span>
          <span>Print All QR Cards</span>
        </button>
      </div>

      {slug && <VenueSettings slug={slug} />}

      {/* Grid of Tables */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 print:grid-cols-2 print:gap-8">
        {tables.map((table) => (
          <div
            key={table.id}
            className="mise-card flex flex-col items-center text-center space-y-4 print:bg-white print:text-black print:border-black print:shadow-none break-inside-avoid"
          >
            {/* Table Label */}
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-terracotta print:text-ink-muted">
                {table.kind === "counter" ? "Counter QR · pay first, then collect" : "Dining Table"}
              </span>
              <h2 className="text-2xl font-black text-ink print:text-black mt-0.5">
                {table.label}
              </h2>
            </div>

            {/* QR Code Graphic */}
            <div className="p-3 bg-white rounded-2xl shadow-md border border-line">
              {table.qrDataUrl ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={table.qrDataUrl}
                  alt={`QR code for ${table.label}`}
                  className="w-56 h-56 object-contain"
                />
              ) : (
                <div className="w-56 h-56 flex items-center justify-center text-ink-muted text-xs">
                  Generating QR...
                </div>
              )}
            </div>

            {/* URL info */}
            <div className="w-full space-y-1">
              <p className="text-[11px] font-mono text-ink-muted print:text-ink-muted break-all select-all">
                {table.guest_url}
              </p>
              <p className="text-[10px] text-ink-muted print:text-ink-muted">
                Scan with any smartphone camera to browse menu & order.
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
