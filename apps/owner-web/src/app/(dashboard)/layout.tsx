"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    async function loadConfig() {
      try {
        const res = await fetch("/api/auth/config");
        if (res.ok) {
          const data = await res.json();
          setDemoMode(Boolean(data.demo_mode));
        }
      } catch {
        // Ignore network errors in config load
      }
    }
    loadConfig();
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.push("/login");
    }
  };

  const navLinks = [
    { href: "/", label: "Live Orders" },
    { href: "/tables", label: "Tables & QR" },
    { href: "/menu", label: "Menu & Safety" },
    { href: "/menu/ingest", label: "Menu Ingest (VLM)" },
    { href: "/brief", label: "Revenue Brief" },
    { href: "/ai", label: "What-if" },
    { href: "/kitchen", label: "Kitchen Display ↗" },
  ];

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col font-sans">
      {/* Demo Banner */}
      {demoMode && (
        <div className="bg-warn-bg border-b border-warn-fg/30 text-warn-fg px-4 py-1.5 text-center text-xs font-semibold backdrop-blur-md sticky top-0 z-50">
          ⚠️ Demo environment: synthetic data
        </div>
      )}

      {/* Dashboard Top Navigation */}
      <header className="sticky top-0 z-40 bg-card backdrop-blur-md border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl mise-card p-1.5 flex items-center justify-center">
                <Image
                  src="/brand/logo-mark.svg"
                  alt="Mise Logo"
                  width={28}
                  height={28}
                  className="w-7 h-7"
                  priority
                />
              </div>
              <div>
                <span className="font-extrabold text-sm tracking-tight text-terracotta block">
                  Mise Operations
                </span>
                <span className="text-[10px] text-ink-muted block -mt-0.5">
                  Revenue Copilot
                </span>
              </div>
            </Link>

            <nav className="hidden lg:flex items-center gap-1">
              {navLinks.map((link) => {
                const isActive = pathname === link.href;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`min-h-[44px] px-3 py-2 rounded-xl text-xs font-semibold inline-flex items-center transition-all ${
                      isActive
                        ? "bg-terracotta/10 text-terracotta border border-terracotta shadow-sm"
                        : "text-ink-muted hover:text-ink hover:bg-white/5"
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleLogout}
              className="btn-ghost !min-h-[38px] !py-1.5 !px-3.5 !text-xs"
            >
              Sign Out
            </button>
          </div>
        </div>

        {/* Mobile secondary navigation */}
        <div className="lg:hidden flex items-center gap-1 px-4 py-2 overflow-x-auto border-t border-line bg-paper">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs font-medium ${
                  isActive
                    ? "bg-terracotta/10 text-terracotta"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>
    </div>
  );
}
