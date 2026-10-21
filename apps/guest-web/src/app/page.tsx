"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import QRCode from "qrcode";

interface AuthConfig {
  demo_mode: boolean;
}

interface DemoInfo {
  guest_url: string;
  owner_url: string;
  kitchen_url: string;
  qr_token: string;
  table_label: string;
}

export default function HomePage() {
  const [loading, setLoading] = useState(true);
  const [demoMode, setDemoMode] = useState<boolean | null>(null);
  const [demoInfo, setDemoInfo] = useState<DemoInfo | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string>("");

  useEffect(() => {
    let isMounted = true;

    async function loadData() {
      try {
        const configRes = await fetch("/api/auth/config");
        if (!configRes.ok) {
          if (isMounted) {
            setDemoMode(false);
            setLoading(false);
          }
          return;
        }

        const configData: AuthConfig = await configRes.json();
        if (isMounted) {
          setDemoMode(Boolean(configData.demo_mode));
        }

        if (configData.demo_mode) {
          try {
            const demoRes = await fetch("/api/demo/info");
            if (demoRes.ok) {
              const infoData: DemoInfo = await demoRes.json();
              if (isMounted) {
                setDemoInfo(infoData);
                const url = await QRCode.toDataURL(infoData.guest_url, {
                  width: 240,
                  margin: 1,
                  color: {
                    dark: "#2B2118",
                    light: "#FBF7F0",
                  },
                });
                setQrDataUrl(url);
              }
            }
          } catch {
            // Fallback demo table link
            const fallbackUrl = "http://localhost:3000/q/demo";
            if (isMounted) {
              const url = await QRCode.toDataURL(fallbackUrl, {
                width: 240,
                margin: 1,
                color: {
                  dark: "#2B2118",
                  light: "#FBF7F0",
                },
              });
              setQrDataUrl(url);
            }
          }
        }
      } catch {
        if (isMounted) {
          setDemoMode(false);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadData();

    return () => {
      isMounted = false;
    };
  }, []);

  // When demo_mode is false, show minimal "scan a table QR code" page
  if (!loading && demoMode === false) {
    return (
      <main className="min-h-screen bg-paper text-ink flex flex-col items-center justify-center p-6 text-center">
        <div className="mise-card p-8 sm:p-12 max-w-md w-full space-y-6">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mise-card p-3 mx-auto">
            <Image
              src="/brand/logo-mark.svg"
              alt="Mise Logo"
              width={48}
              height={48}
              priority
            />
          </div>
          <div className="space-y-2">
            <h1 className="text-2xl font-extrabold tracking-tight">
              Welcome to <span className="text-terracotta">Mise</span>
            </h1>
            <p className="text-sm text-ink-muted">
              Please scan the QR code located on your dining table to explore our menu, filter allergens, and place your order.
            </p>
          </div>
          <div className="p-4 rounded-xl bg-card border border-line flex items-center justify-center gap-3">
            <span className="text-2xl">📱</span>
            <span className="text-xs text-ink-muted font-medium">
              Camera / QR scanner ready
            </span>
          </div>
        </div>
      </main>
    );
  }

  const guestUrl = demoInfo?.guest_url ?? "http://localhost:3000/q/demo";
  const ownerUrl = demoInfo?.owner_url ?? "http://localhost:3001";
  const kitchenUrl = demoInfo?.kitchen_url ?? "http://localhost:3001/kitchen";

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col selection:bg-terracotta/10 selection:text-terracotta">
      {/* Demo Environment Top Banner */}
      <div className="bg-warn-bg border-b border-warn-fg/30 text-warn-fg px-4 py-2 text-center text-xs font-semibold backdrop-blur-md">
        ⚠️ Demo environment: synthetic data
      </div>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 sm:px-6 lg:px-8 space-y-12">
        {/* HERO SECTION */}
        <section className="mise-card overflow-hidden p-6 sm:p-10 relative">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            <div className="lg:col-span-7 space-y-4">
              <div className="inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-paper-2 border border-line">
                <Image
                  src="/brand/logo-mark.svg"
                  alt="Mise Mark"
                  width={20}
                  height={20}
                  className="w-5 h-5"
                  priority
                />
                <span className="text-xs font-bold uppercase tracking-wider text-terracotta">
                  Live demo
                </span>
              </div>

              <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight">
                Mise: <span className="text-terracotta">Restaurant Revenue Copilot</span>
              </h1>

              <p className="text-base sm:text-lg text-ink-muted leading-relaxed">
                Ordering, kitchen display and revenue analytics for independent restaurants.
              </p>

              <div className="pt-2 flex flex-wrap gap-3">
                <a
                  href={guestUrl}
                  className="btn-primary min-h-[44px] shadow-lg shadow-ink/10"
                >
                  🚀 Order as Guest (Table 1)
                </a>
                <a
                  href={ownerUrl}
                  className="btn-ghost min-h-[44px]"
                >
                  📊 Owner Dashboard
                </a>
                <a
                  href={kitchenUrl}
                  className="btn-ghost min-h-[44px]"
                >
                  🍳 Kitchen Display
                </a>
              </div>
            </div>

            <div className="lg:col-span-5 relative aspect-[16/10] sm:aspect-[4/3] rounded-2xl overflow-hidden border border-line shadow-2xl">
              <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-card via-paper to-card">
                <Image
                  src="/brand/logo-mark.svg"
                  alt="Mise logo"
                  width={160}
                  height={160}
                  priority
                  className="opacity-90"
                />
              </div>
            </div>
          </div>
        </section>

        {/* THREE CORE CARDS */}
        <section className="space-y-4">
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-ink">
            Live Interactive Applications
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Card 1: Guest Ordering */}
            <div className="mise-card flex flex-col justify-between space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-terracotta">
                    Guest Experience
                  </span>
                  <span className="chip chip-safe">
                    {demoInfo?.table_label ?? "Table 1"}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-ink">
                  Order as a guest
                </h3>
                <p className="text-xs text-ink-muted leading-relaxed">
                  Interactive multi-lingual menu with EU-14 allergen avoidance, verified safety vector matching, and instant carting.
                </p>

                {/* QR Code Container */}
                <div className="p-4 rounded-xl bg-ink flex flex-col items-center justify-center space-y-2">
                  {qrDataUrl ? (
                    <Image
                      src={qrDataUrl}
                      alt="Guest Table QR Code"
                      width={180}
                      height={180}
                      className="rounded-lg shadow-sm"
                      unoptimized
                    />
                  ) : (
                    <div className="w-[180px] h-[180px] flex items-center justify-center text-xs text-ink-muted">
                      Generating QR...
                    </div>
                  )}
                  <span className="text-[10px] font-semibold text-cream uppercase tracking-wider">
                    Scan with camera or click below
                  </span>
                </div>
              </div>

              <a
                href={guestUrl}
                className="btn-primary w-full text-center"
              >
                Launch Guest Order →
              </a>
            </div>

            {/* Card 2: Kitchen Display */}
            <div className="mise-card flex flex-col justify-between space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-warn-fg">
                    Back of House
                  </span>
                  <span className="chip chip-unverified">
                    Live SSE Queue
                  </span>
                </div>
                <h3 className="text-lg font-bold text-ink">
                  Kitchen display
                </h3>
                <p className="text-xs text-ink-muted leading-relaxed">
                  Near-black high contrast KDS. Real-time ticket age coloring, prominent red allergy alerts from immutable order snapshots, audio dings, and wake lock.
                </p>

                <div className="p-4 rounded-xl bg-paper border border-line space-y-2.5">
                  <div className="border-l-4 border-olive pl-3 py-1">
                    <div className="text-xs font-bold text-ink">Table 1 • 2 items</div>
                    <div className="text-[11px] text-ink-muted">0m ago • New</div>
                  </div>
                  <div className="p-2 rounded bg-danger-bg border border-danger-fg text-[10px] font-bold text-danger-fg uppercase tracking-wide">
                    🚨 Allergy Flag: Gluten, Nuts
                  </div>
                </div>
              </div>

              <a
                href={kitchenUrl}
                className="btn-ghost w-full text-center"
              >
                Open Kitchen Display →
              </a>
            </div>

            {/* Card 3: Owner Dashboard */}
            <div className="mise-card flex flex-col justify-between space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-terracotta">
                    Operations & AI
                  </span>
                  <span className="chip chip-safe">
                    Revenue Copilot
                  </span>
                </div>
                <h3 className="text-lg font-bold text-ink">
                  Owner dashboard
                </h3>
                <p className="text-xs text-ink-muted leading-relaxed">
                  Revenue brief with menu engineering and a backtested forecast, what-if calculator, and VLM menu ingest.
                </p>

                <div className="space-y-2">
                  <a
                    href={`${ownerUrl}/brief`}
                    className="block p-2.5 rounded-xl bg-paper border border-line hover:border-terracotta transition-colors text-xs text-ink font-semibold"
                  >
                    📈 Revenue Brief & Forecast →
                  </a>
                  <a
                    href={`${ownerUrl}/menu/ingest`}
                    className="block p-2.5 rounded-xl bg-paper border border-line hover:border-terracotta transition-colors text-xs text-ink font-semibold"
                  >
                    📸 VLM Menu Ingest & Verification →
                  </a>
                  <a
                    href={`${ownerUrl}/ai`}
                    className="block p-2.5 rounded-xl bg-paper border border-line hover:border-terracotta transition-colors text-xs text-ink font-semibold"
                  >
                    🔮 What-if Calculator →
                  </a>
                </div>
              </div>

              <a
                href={ownerUrl}
                className="btn-primary w-full text-center"
              >
                Open Owner Dashboard →
              </a>
            </div>
          </div>
        </section>

        {/* GUIDED TOUR */}
        <section className="mise-card p-6 sm:p-8 space-y-6">
          <div className="border-b border-line pb-4">
            <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-ink">
              Guided tour (3 minutes)
            </h2>
            <p className="text-xs sm:text-sm text-ink-muted mt-1">
              Follow this step-by-step walkthrough from guest order to kitchen ticket to owner analytics:
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-4 rounded-xl bg-card border border-line space-y-2">
              <div className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-terracotta/10 border border-terracotta text-xs font-bold text-terracotta">
                1
              </div>
              <h4 className="text-sm font-bold text-ink">
                Minute 1: Guest Ordering
              </h4>
              <p className="text-xs text-ink-muted leading-relaxed">
                Open <span className="text-terracotta">Table 1</span> link. Select dietary tags and EU-14 allergen filters. Observe dynamic vector matching and place an order.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-card border border-line space-y-2">
              <div className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-warn-bg border border-warn-fg/30 text-xs font-bold text-warn-fg">
                2
              </div>
              <h4 className="text-sm font-bold text-ink">
                Minute 2: Kitchen Display (KDS)
              </h4>
              <p className="text-xs text-ink-muted leading-relaxed">
                Switch to <span className="text-warn-fg">Kitchen Display</span>. The order arrives instantly via SSE with bold allergy banners and age-color borders. Bump to complete.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-card border border-line space-y-2">
              <div className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-safe-bg border border-olive text-xs font-bold text-olive">
                3
              </div>
              <h4 className="text-sm font-bold text-ink">
                Minute 3: Owner Copilot
              </h4>
              <p className="text-xs text-ink-muted leading-relaxed">
                Open the <span className="text-olive">Owner Dashboard</span>. Generate demo data on the Revenue Brief, try the menu image ingest with VLM, and run a what-if price change.
              </p>
            </div>
          </div>
        </section>

        {/* FOOTER */}
        <footer className="pt-6 pb-12 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-line text-xs text-ink-muted">
          <div className="flex items-center gap-2">
            <Image
              src="/brand/logo-mark.svg"
              alt="Mise Logo"
              width={16}
              height={16}
              className="w-4 h-4"
            />
            <span>Mise Restaurant Platform © 2026</span>
          </div>
        </footer>
      </main>
    </div>
  );
}

