"use client";

import React, { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { BOWL, FLAME } from "./logo";

gsap.registerPlugin(useGSAP);

/** True when the guest prefers reduced motion; false on the server and where `matchMedia` is missing. */
function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false), []);
  return reduced;
}

/** The logo's lamp: its flame flickers in the bowl. The venue's still mark under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".nz-flame", { scaleY: 0.78, scaleX: 1.1, transformOrigin: "50% 100%", duration: 0.16, repeat: -1, yoyo: true, ease: "sine.inOut" });
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      {reduced ? (
        // eslint-disable-next-line @next/next/no-img-element -- a small static mark
        <img src="/venues/noor-and-zaatar/mark.svg" alt="" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"} />
      ) : (
        <svg aria-hidden="true" viewBox="15 25 170 162" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"}>
          <path d={BOWL} fill="var(--brand-accent)" />
          <path className="nz-flame" d={FLAME} fill="var(--brand-spark)" />
        </svg>
      )}
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
