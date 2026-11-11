"use client";

import React from "react";
import { useVenue } from "./BrandShell";

/** The venue's band at the top of the menu: light logo lockup on the deep colour, then its motif. */
export function Masthead() {
  const { slug, name, branded, Motif } = useVenue();
  return (
    <div className="bg-[var(--brand-deep)] text-[var(--brand-on-deep)]">
      <div className="mx-auto flex max-w-2xl justify-center px-4 py-5">
        {branded ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`/venues/${slug}/lockup.svg`} alt={name} className="h-20 max-w-[70%] object-contain" />
        ) : (
          <h1 className="text-2xl">{name}</h1>
        )}
      </div>
      <Motif variant="masthead" />
    </div>
  );
}
