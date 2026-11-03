"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AppShell, Card, type AppShellProps, type NavGroup } from "ui";
import { VenueProvider, useVenue, useSlugRef } from "../../lib/venue";
import type { FloorResponse } from "../../lib/floor";

const navGroups = (floorLabel: React.ReactNode): NavGroup[] => [
  {
    label: "Service",
    items: [
      { href: "/floor", label: floorLabel },
      { href: "/bills", label: "Bills" },
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

/** Red + amber floor tiles for the current venue, polled every 30 s; null until known. */
function useFloorCount(): number | null {
  const { venue } = useVenue();
  const slug = venue?.slug;
  const slugRef = useSlugRef(slug);
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    setCount(null);
    if (!slug) return;
    let seq = 0;
    const load = async () => {
      const mine = ++seq;
      try {
        const res = await fetch(`/api/restaurants/${slug}/floor`);
        if (!res.ok) return;
        const body = (await res.json()) as FloorResponse;
        if (mine === seq && slugRef.current === slug) setCount(body.counts.red + body.counts.amber);
      } catch {
        // keep the last count; the next poll retries
      }
    };
    void load();
    const timer = setInterval(load, 30_000);
    return () => {
      seq++; // drop responses still in flight for this venue
      clearInterval(timer);
    };
  }, [slug, slugRef]);

  return count;
}

/** AppShell with the "Floor (n)" badge; polls once for both the sidebar and the phone tab bar. */
function DashboardShell(props: Omit<AppShellProps, "groups">) {
  const count = useFloorCount();
  const floor = (
    <span className="flex items-center justify-between gap-2">
      Floor
      {count ? (
        <span className="chip chip-contains">
          <span aria-hidden="true">{count}</span>
          <span className="sr-only">{count} tables need attention</span>
        </span>
      ) : null}
    </span>
  );
  return <AppShell groups={navGroups(floor)} {...props} />;
}

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
        className="mt-1 w-full rounded-lg border border-line bg-paper px-2 py-1 text-sm text-ink-muted focus:outline-none focus:border-terracotta focus:ring-1 focus:ring-terracotta"
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
  const { error, retry } = useVenue();
  if (error === "unauthorized") return null; // the provider is redirecting to /login
  if (error === "failed") {
    return (
      <Card className="mx-auto mt-12 max-w-md space-y-4 p-6 text-center">
        <p role="alert" className="text-sm text-ink">
          Couldn&apos;t load your restaurants. Try again.
        </p>
        <button onClick={retry} className="btn-primary w-full">
          Retry
        </button>
      </Card>
    );
  }
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
      <DashboardShell
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
      </DashboardShell>
    </VenueProvider>
  );
}
