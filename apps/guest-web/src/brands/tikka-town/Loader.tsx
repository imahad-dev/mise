"use client";

import React, { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { SKEWER_MARK } from "./logo";

gsap.registerPlugin(useGSAP);

/** True when the guest prefers reduced motion; false on the server and where `matchMedia` is missing. */
function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false), []);
  return reduced;
}

/** The logo's skewer turns on the grill; the venue's still mark under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".tt-skewer", { rotate: 360, svgOrigin: "100 100", duration: 1.2, ease: "none", repeat: -1 });
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      {reduced ? (
        // eslint-disable-next-line @next/next/no-img-element -- a small static mark
        <img src="/venues/tikka-town/mark.svg" alt="" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"} />
      ) : (
        <svg aria-hidden="true" viewBox="10 10 180 180" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"}>
          <path className="tt-skewer" d={SKEWER_MARK} fill="var(--brand-accent)" />
        </svg>
      )}
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
