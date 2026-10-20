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
                    dark: "#070B10",
                    light: "#F3F8FC",
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
                  dark: "#070B10",
                  light: "#F3F8FC",
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
      <main className="min-h-screen bg-[#070B10] text-[#F3F8FC] flex flex-col items-center justify-center p-6 text-center">
        <div className="glass-panel p-8 sm:p-12 max-w-md w-full space-y-6">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl glass-panel p-3 mx-auto">
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
              Welcome to <span className="gradient-text">Mise</span>
            </h1>
            <p className="text-sm text-[#8FA3B3]">
              Please scan the QR code located on your dining table to explore our menu, filter allergens, and place your order.
            </p>
          </div>
          <div className="p-4 rounded-xl bg-[#0D141B] border border-[#38BDF8]/20 flex items-center justify-center gap-3">
            <span className="text-2xl">📱</span>
            <span className="text-xs text-[#8FA3B3] font-medium">
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
    <div className="min-h-screen bg-[#070B10] text-[#F3F8FC] flex flex-col selection:bg-[#22D3EE]/20 selection:text-[#22D3EE]">
      {/* Demo Environment Top Banner */}
      <div className="bg-[#FF9F2E]/10 border-b border-[#FF9F2E]/30 text-[#FF9F2E] px-4 py-2 text-center text-xs font-semibold backdrop-blur-md">
        ⚠️ Demo environment: synthetic data
      </div>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 sm:px-6 lg:px-8 space-y-12">
        {/* HERO SECTION */}
        <section className="glass-panel overflow-hidden p-6 sm:p-10 relative">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            <div className="lg:col-span-7 space-y-4">
              <div className="inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-[#38BDF8]/10 border border-[#38BDF8]/30">
                <Image
                  src="/brand/logo-mark.svg"
                  alt="Mise Mark"
                  width={20}
                  height={20}
                  className="w-5 h-5"
                  priority
                />
                <span className="text-xs font-bold uppercase tracking-wider text-[#22D3EE]">
                  Live demo
                </span>
              </div>

              <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight">
                Mise: <span className="gradient-text">Restaurant Revenue Copilot</span>
              </h1>

              <p className="text-base sm:text-lg text-[#8FA3B3] leading-relaxed">
                Ordering, kitchen display and revenue analytics for independent restaurants.
              </p>

              <div className="pt-2 flex flex-wrap gap-3">
                <a
                  href={guestUrl}
                  className="btn-primary min-h-[44px] shadow-lg shadow-cyan-950/40"
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

            <div className="lg:col-span-5 relative aspect-[16/10] sm:aspect-[4/3] rounded-2xl overflow-hidden border border-[#38BDF8]/20 shadow-2xl">
              <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-[#0D141B] via-[#070B10] to-[#0D141B]">
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
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-[#F3F8FC]">
            Live Interactive Applications
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Card 1: Guest Ordering */}
            <div className="mise-card flex flex-col justify-between space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#22D3EE]">
                    Guest Experience
                  </span>
                  <span className="chip chip-safe">
                    {demoInfo?.table_label ?? "Table 1"}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-[#F3F8FC]">
                  Order as a guest
                </h3>
                <p className="text-xs text-[#8FA3B3] leading-relaxed">
                  Interactive multi-lingual menu with EU-14 allergen avoidance, verified safety vector matching, and instant carting.
                </p>

                {/* QR Code Container */}
                <div className="p-4 rounded-xl bg-[#F3F8FC] flex flex-col items-center justify-center space-y-2">
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
                    <div className="w-[180px] h-[180px] flex items-center justify-center text-xs text-zinc-600">
                      Generating QR...
                    </div>
                  )}
                  <span className="text-[10px] font-semibold text-[#070B10] uppercase tracking-wider">
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
                  <span className="text-xs font-bold uppercase tracking-wider text-[#FF9F2E]">
                    Back of House
                  </span>
                  <span className="chip chip-unverified">
                    Live SSE Queue
                  </span>
                </div>
                <h3 className="text-lg font-bold text-[#F3F8FC]">
                  Kitchen display
                </h3>
                <p className="text-xs text-[#8FA3B3] leading-relaxed">
                  Near-black high contrast KDS. Real-time ticket age coloring, prominent red allergy alerts from immutable order snapshots, audio dings, and wake lock.
                </p>

                <div className="p-4 rounded-xl bg-[#070B10] border border-[#38BDF8]/15 space-y-2.5">
                  <div className="border-l-4 border-[#34D399] pl-3 py-1">
                    <div className="text-xs font-bold text-[#F3F8FC]">Table 1 • 2 items</div>
                    <div className="text-[11px] text-[#8FA3B3]">0m ago • New</div>
                  </div>
                  <div className="p-2 rounded bg-[#EF4444]/20 border border-[#EF4444]/40 text-[10px] font-bold text-[#EF4444] uppercase tracking-wide">
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
                  <span className="text-xs font-bold uppercase tracking-wider text-[#2F7BFF]">
                    Operations & AI
                  </span>
                  <span className="chip chip-safe">
                    Revenue Copilot
                  </span>
                </div>
                <h3 className="text-lg font-bold text-[#F3F8FC]">
                  Owner dashboard
                </h3>
                <p className="text-xs text-[#8FA3B3] leading-relaxed">
                  Revenue brief with menu engineering and a backtested forecast, what-if calculator, and VLM menu ingest.
                </p>

                <div className="space-y-2">
                  <a
                    href={`${ownerUrl}/brief`}
                    className="block p-2.5 rounded-xl bg-[#070B10] border border-[#38BDF8]/15 hover:border-[#22D3EE]/40 transition-colors text-xs text-[#F3F8FC] font-semibold"
                  >
                    📈 Revenue Brief & Forecast →
                  </a>
                  <a
                    href={`${ownerUrl}/menu/ingest`}
                    className="block p-2.5 rounded-xl bg-[#070B10] border border-[#38BDF8]/15 hover:border-[#22D3EE]/40 transition-colors text-xs text-[#F3F8FC] font-semibold"
                  >
                    📸 VLM Menu Ingest & Verification →
                  </a>
                  <a
                    href={`${ownerUrl}/ai`}
                    className="block p-2.5 rounded-xl bg-[#070B10] border border-[#38BDF8]/15 hover:border-[#22D3EE]/40 transition-colors text-xs text-[#F3F8FC] font-semibold"
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
        <section className="glass-panel p-6 sm:p-8 space-y-6">
          <div className="border-b border-[#38BDF8]/15 pb-4">
            <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-[#F3F8FC]">
              Guided tour (3 minutes)
            </h2>
            <p className="text-xs sm:text-sm text-[#8FA3B3] mt-1">
              Follow this step-by-step walkthrough from guest order to kitchen ticket to owner analytics:
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-4 rounded-xl bg-[#0D141B] border border-[#38BDF8]/15 space-y-2">
              <div className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[#2F7BFF]/20 border border-[#2F7BFF] text-xs font-bold text-[#22D3EE]">
                1
              </div>
              <h4 className="text-sm font-bold text-[#F3F8FC]">
                Minute 1: Guest Ordering
              </h4>
              <p className="text-xs text-[#8FA3B3] leading-relaxed">
                Open <span className="text-[#22D3EE]">Table 1</span> link. Select dietary tags and EU-14 allergen filters. Observe dynamic vector matching and place an order.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-[#0D141B] border border-[#38BDF8]/15 space-y-2">
              <div className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[#FF9F2E]/20 border border-[#FF9F2E] text-xs font-bold text-[#FF9F2E]">
                2
              </div>
              <h4 className="text-sm font-bold text-[#F3F8FC]">
                Minute 2: Kitchen Display (KDS)
              </h4>
              <p className="text-xs text-[#8FA3B3] leading-relaxed">
                Switch to <span className="text-[#FF9F2E]">Kitchen Display</span>. The order arrives instantly via SSE with bold allergy banners and age-color borders. Bump to complete.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-[#0D141B] border border-[#38BDF8]/15 space-y-2">
              <div className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[#34D399]/20 border border-[#34D399] text-xs font-bold text-[#34D399]">
                3
              </div>
              <h4 className="text-sm font-bold text-[#F3F8FC]">
                Minute 3: Owner Copilot
              </h4>
              <p className="text-xs text-[#8FA3B3] leading-relaxed">
                Open the <span className="text-[#34D399]">Owner Dashboard</span>. Generate demo data on the Revenue Brief, try the menu image ingest with VLM, and run a what-if price change.
              </p>
            </div>
          </div>
        </section>

        {/* FOOTER */}
        <footer className="pt-6 pb-12 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-[#38BDF8]/15 text-xs text-[#8FA3B3]">
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

