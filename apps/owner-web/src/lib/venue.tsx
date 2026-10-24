"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

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

interface VenueState {
  venues: Venue[];
  venue: Venue | null;
  loading: boolean;
  select: (slug: string) => void;
}

const VenueContext = createContext<VenueState>({ venues: [], venue: null, loading: true, select: () => {} });

export function VenueProvider({ children }: { children: React.ReactNode }) {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venue, setVenue] = useState<Venue | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/restaurants")
      .then((r) => (r.ok ? r.json() : { restaurants: [] }))
      .then((d: { restaurants: Venue[] }) => {
        setVenues(d.restaurants);
        setVenue(pickVenue(d.restaurants, readStoredSlug()));
      })
      .catch(() => setVenues([]))
      .finally(() => setLoading(false));
  }, []);

  const select = (slug: string) => {
    const next = venues.find((v) => v.slug === slug);
    if (next) {
      storeSlug(slug);
      setVenue(next);
    }
  };

  return <VenueContext.Provider value={{ venues, venue, loading, select }}>{children}</VenueContext.Provider>;
}

export const useVenue = () => useContext(VenueContext);
