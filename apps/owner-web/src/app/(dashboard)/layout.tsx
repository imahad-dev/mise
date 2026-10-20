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
    <div className="min-h-screen bg-[#070B10] text-[#F3F8FC] flex flex-col font-sans">
      {/* Demo Banner */}
      {demoMode && (
        <div className="bg-[#FF9F2E]/10 border-b border-[#FF9F2E]/30 text-[#FF9F2E] px-4 py-1.5 text-center text-xs font-semibold backdrop-blur-md sticky top-0 z-50">
          ⚠️ Demo environment: synthetic data
        </div>
      )}

      {/* Dashboard Top Navigation */}
      <header className="sticky top-0 z-40 bg-[#0D141B]/90 backdrop-blur-md border-b border-[#38BDF8]/15">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl glass-panel p-1.5 flex items-center justify-center">
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
                <span className="font-extrabold text-sm tracking-tight gradient-text block">
                  Mise Operations
                </span>
                <span className="text-[10px] text-[#8FA3B3] block -mt-0.5">
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
                        ? "bg-[#2F7BFF]/15 text-[#22D3EE] border border-[#22D3EE]/30 shadow-sm"
                        : "text-[#8FA3B3] hover:text-[#F3F8FC] hover:bg-white/5"
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
        <div className="lg:hidden flex items-center gap-1 px-4 py-2 overflow-x-auto border-t border-[#38BDF8]/10 bg-[#070B10]">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs font-medium ${
                  isActive
                    ? "bg-[#2F7BFF]/20 text-[#22D3EE]"
                    : "text-[#8FA3B3] hover:text-[#F3F8FC]"
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
