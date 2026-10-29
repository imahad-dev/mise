"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

export interface Venue {
  slug: string;
  name: string;
  city: string | null;
  currency: string;
  role: "owner" | "staff";
}

const KEY = "mise.venue";

export function readStoredSlug(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function storeSlug(slug: string): void {
  try {
    window.localStorage.setItem(KEY, slug);
  } catch {
    // Storage blocked: the choice lasts for this page view only.
  }
}

export function pickVenue(venues: Venue[], stored: string | null): Venue | null {
  return venues.find((v) => v.slug === stored) ?? venues[0] ?? null;
}

export type VenueError = "unauthorized" | "no_venues" | "failed" | null;

/** Decide the provider error from the /api/restaurants response (status null = network failure). */
export function venueError(status: number | null, venues: Venue[]): VenueError {
  if (status === 401) return "unauthorized";
  if (status === null || status < 200 || status >= 300) return "failed";
  return venues.length === 0 ? "no_venues" : null;
}

/** Where to go after sign-in: staff-only accounts open the kitchen display. */
export function landingPath(venues: Venue[]): "/" | "/kitchen" {
  return venues.length > 0 && venues.every((v) => v.role === "staff") ? "/kitchen" : "/";
}

interface VenueState {
  venues: Venue[];
  venue: Venue | null;
  loading: boolean;
  error: VenueError;
  select: (slug: string) => void;
  retry: () => void;
}

const VenueContext = createContext<VenueState>({ venues: [], venue: null, loading: true, error: null, select: () => {}, retry: () => {} });

export function VenueProvider({ children }: { children: React.ReactNode }) {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venue, setVenue] = useState<Venue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<VenueError>(null);
  const router = useRouter();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch("/api/restaurants")
      .then(async (r) => {
        const list: Venue[] = r.ok ? ((await r.json()) as { restaurants: Venue[] }).restaurants : [];
        const err = venueError(r.status, list);
        setVenues(list);
        setVenue(pickVenue(list, readStoredSlug()));
        setError(err);
        if (err === "unauthorized") router.push("/login");
      })
      .catch(() => {
        setVenues([]);
        setVenue(null);
        setError(venueError(null, []));
      })
      .finally(() => setLoading(false));
  }, [router]);

  useEffect(load, [load]);

  const select = (slug: string) => {
    const next = venues.find((v) => v.slug === slug);
    if (next) {
      storeSlug(slug);
      setVenue(next);
    }
  };

  return <VenueContext.Provider value={{ venues, venue, loading, error, select, retry: load }}>{children}</VenueContext.Provider>;
}

export const useVenue = () => useContext(VenueContext);

/** Ref that always holds the current slug, so async work can drop results for a venue the user left. */
export function useSlugRef(slug: string | undefined) {
  const ref = useRef(slug);
  ref.current = slug;
  return ref;
}
