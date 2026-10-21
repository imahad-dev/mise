"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AppShell, type NavGroup } from "ui";

const NAV: NavGroup[] = [
  {
    label: "Service",
    items: [
      { href: "/", label: "Live orders" },
      { href: "/kitchen", label: "Kitchen display ↗" },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/brief", label: "Revenue Brief" },
      { href: "/ai", label: "What-if" },
    ],
  },
  {
    label: "Menu",
    items: [
      { href: "/menu", label: "Menu & allergens" },
      { href: "/menu/ingest", label: "Import from photo" },
    ],
  },
  { label: "Setup", items: [{ href: "/tables", label: "Tables & QR" }] },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    fetch("/api/auth/config")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDemoMode(Boolean(d?.demo_mode)))
      .catch(() => setDemoMode(false));
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.push("/login");
    }
  };

  return (
    <AppShell
      groups={NAV}
      currentPath={pathname}
      linkAs={Link}
      banner={
        demoMode && (
          <div className="border-b border-warn-fg/30 bg-warn-bg px-4 py-1.5 text-center text-xs font-semibold text-warn-fg">
            Demo environment: synthetic data
          </div>
        )
      }
      brand={
        <Link href="/" className="flex items-center gap-3 px-2">
          <Image src="/brand/logo-mark.svg" alt="" width={32} height={32} priority />
          <span>
            <span className="block font-serif text-lg font-bold leading-tight">Mise</span>
            <span className="block text-xs text-ink-muted">Trattoria da Mario</span>
          </span>
        </Link>
      }
      sidebarFooter={
        <button onClick={handleLogout} className="btn-ghost md:mt-4 md:w-full">
          Sign out
        </button>
      }
    >
      {children}
    </AppShell>
  );
}
