"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AppShell, Card, type NavGroup } from "ui";
import { VenueProvider, useVenue } from "../../lib/venue";

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

function VenueSwitcher() {
  const { venues, venue, select } = useVenue();
  if (!venue) return null;
  const label = (v: { name: string; city: string | null }) => (v.city ? `${v.name} · ${v.city}` : v.name);
  if (venues.length > 1) {
    return (
      <select
        aria-label="Venue"
        value={venue.slug}
        onChange={(e) => select(e.target.value)}
        className="mt-1 w-full rounded-lg border border-line bg-paper px-2 py-1 text-sm text-ink-muted"
      >
        {venues.map((v) => (
          <option key={v.slug} value={v.slug}>
            {label(v)}
          </option>
        ))}
      </select>
    );
  }
  return <span className="mt-1 block px-2 text-sm text-ink-muted">{label(venue)}</span>;
}

function VenueGate({ children, onSignOut }: { children: React.ReactNode; onSignOut: () => void }) {
  const { error } = useVenue();
  if (error !== "no_venues") return <>{children}</>;
  return (
    <Card className="mx-auto mt-12 max-w-md space-y-4 p-6 text-center">
      <p className="text-sm text-ink">This account is not linked to a restaurant yet.</p>
      <button onClick={onSignOut} className="btn-ghost w-full">
        Sign out
      </button>
    </Card>
  );
}

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
    <VenueProvider>
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
          <div>
            <Link href="/" className="flex items-center gap-3 px-2">
              <Image src="/brand/logo-mark.svg" alt="" width={32} height={32} priority />
              <span>
                <span className="block font-serif text-lg font-bold leading-tight">Mise</span>
              </span>
            </Link>
            <VenueSwitcher />
          </div>
        }
        sidebarFooter={
          <button onClick={handleLogout} className="btn-ghost md:mt-4 md:w-full">
            Sign out
          </button>
        }
      >
        <VenueGate onSignOut={handleLogout}>{children}</VenueGate>
      </AppShell>
    </VenueProvider>
  );
}
