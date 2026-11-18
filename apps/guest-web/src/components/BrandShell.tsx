"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { NEUTRAL_TOKENS, venueBrand } from "ui";
import { loadBrand } from "../brands";
import { brandStyle } from "../brands/style";
import type { BrandPackage } from "../brands/types";
import { claimWelcome } from "../lib/welcome";
import { NeutralLoader } from "./NeutralLoader";

export interface Venue {
  slug: string;
  name: string;
  languages?: string[];
  defaultLanguage?: string;
}

interface VenueContextValue extends Venue {
  branded: boolean;
  Motif: BrandPackage["Motif"];
  Loader: BrandPackage["Loader"];
}

const NoMotif: BrandPackage["Motif"] = () => null;
const VenueContext = createContext<VenueContextValue>({
  slug: "",
  name: "",
  languages: ["en"],
  defaultLanguage: "en",
  branded: false,
  Motif: NoMotif,
  Loader: NeutralLoader,
});

export const useVenue = () => useContext(VenueContext);

class SkipOnError extends React.Component<{ onError: () => void; children: React.ReactNode }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const WELCOME_CAP_MS = 3000;

/** The venue's brand around a guest page. `welcomeFor` is the visit (guest session) id: when
 *  given, the welcome plays once for that visit. The page renders underneath, so ordering never
 *  waits for it. */
export function BrandShell({
  venue,
  welcomeFor,
  children,
}: {
  venue: Venue;
  welcomeFor?: string;
  children: React.ReactNode;
}) {
  const brand = venueBrand(venue.slug);
  const [pkg, setPkg] = useState<BrandPackage | null>(null);
  const [welcome, setWelcome] = useState<"pending" | "shown" | "done">(welcomeFor ? "pending" : "done");

  useEffect(() => {
    let live = true;
    // A chunk request that hangs must not leave the welcome pending forever.
    const cap = setTimeout(() => setWelcome((w) => (w === "pending" ? "done" : w)), WELCOME_CAP_MS);
    loadBrand(venue.slug)
      .then((p) => {
        if (!live) return;
        setPkg(p);
        if (!p) setWelcome("done");
      })
      .catch(() => live && setWelcome("done")); // a failed chunk leaves the neutral fallback
    return () => {
      live = false;
      clearTimeout(cap);
    };
  }, [venue.slug]);

  useEffect(() => {
    if (welcome !== "pending" || !pkg || !welcomeFor) return;
    if (!pkg.Welcome) {
      setWelcome("done"); // nothing to play: do not consume the visit
      return;
    }
    let storage: Storage | null = null;
    try {
      storage = window.sessionStorage;
    } catch {
      storage = null;
    }
    setWelcome(claimWelcome(welcomeFor, storage) ? "shown" : "done");
  }, [welcome, pkg, welcomeFor]);

  useEffect(() => {
    if (welcome !== "shown") return;
    const t = setTimeout(() => setWelcome("done"), WELCOME_CAP_MS);
    return () => clearTimeout(t);
  }, [welcome]);

  const value: VenueContextValue = {
    ...venue,
    branded: Boolean(brand),
    Motif: pkg?.Motif ?? NoMotif,
    Loader: pkg?.Loader ?? NeutralLoader,
  };
  const Welcome = pkg?.Welcome;

  return (
    <VenueContext.Provider value={value}>
      <div
        data-brand={brand ? venue.slug : "neutral"}
        data-welcome={welcome}
        style={brandStyle(brand?.tokens ?? NEUTRAL_TOKENS, brand ?? undefined)}
        className={`min-h-screen ${pkg?.fontClass ?? ""}`}
      >
        {children}
        {welcome === "shown" && Welcome && (
          <div
            data-testid="welcome"
            onClick={() => setWelcome("done")}
            className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--brand-deep)]"
          >
            <SkipOnError onError={() => setWelcome("done")}>
              <Welcome name={venue.name} onDone={() => setWelcome("done")} />
            </SkipOnError>
          </div>
        )}
      </div>
    </VenueContext.Provider>
  );
}
