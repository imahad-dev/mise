"use client";

import React, { useEffect, useState } from "react";
import QRCode from "qrcode";

interface TableItem {
  id: string;
  restaurant_id: string;
  label: string;
  qr_token: string;
  guest_url: string;
  qrDataUrl?: string;
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

export default function TablesPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [tables, setTables] = useState<TableItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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

        setTables(withQr);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    loadTables();
  }, [slug]);

  const handlePrint = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="py-20 text-center">
        <div className="inline-block w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-zinc-500 mt-2">Loading tables & generating QR codes...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-rose-950/60 border border-rose-800 rounded-2xl text-xs text-rose-300">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#38BDF8]/15 pb-4 print:hidden">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">
            Dining Tables & <span className="gradient-text">QR Cards</span>
          </h1>
          <p className="text-xs text-[#8FA3B3] mt-1">
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

      {/* Grid of Tables */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 print:grid-cols-2 print:gap-8">
        {tables.map((table) => (
          <div
            key={table.id}
            className="mise-card flex flex-col items-center text-center space-y-4 print:bg-white print:text-black print:border-black print:shadow-none break-inside-avoid"
          >
            {/* Table Label */}
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#22D3EE] print:text-zinc-600">
                Dining Table
              </span>
              <h2 className="text-2xl font-black text-[#F3F8FC] print:text-black mt-0.5">
                {table.label}
              </h2>
            </div>

            {/* QR Code Graphic */}
            <div className="p-3 bg-white rounded-2xl shadow-md border border-zinc-200">
              {table.qrDataUrl ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={table.qrDataUrl}
                  alt={`QR code for ${table.label}`}
                  className="w-56 h-56 object-contain"
                />
              ) : (
                <div className="w-56 h-56 flex items-center justify-center text-zinc-400 text-xs">
                  Generating QR...
                </div>
              )}
            </div>

            {/* URL info */}
            <div className="w-full space-y-1">
              <p className="text-[11px] font-mono text-[#8FA3B3] print:text-zinc-700 break-all select-all">
                {table.guest_url}
              </p>
              <p className="text-[10px] text-[#8FA3B3]/70 print:text-zinc-500">
                Scan with any smartphone camera to browse menu & order.
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
