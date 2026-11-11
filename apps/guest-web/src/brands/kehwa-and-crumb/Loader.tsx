"use client";

import React, { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** True when the guest prefers reduced motion; false on the server and where `matchMedia` is missing. */
function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false), []);
  return reduced;
}

/** Crumbs fall and gather; the venue's still mark under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          ".kc-bit",
          { y: -6, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.4, stagger: 0.15, repeat: -1, repeatDelay: 0.3, ease: "bounce.out" },
        );
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      {reduced ? (
        {/* eslint-disable-next-line @next/next/no-img-element -- a small static mark */}
        <img src="/venues/kehwa-and-crumb/mark.svg" alt="" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"} />
      ) : (
        <svg aria-hidden="true" viewBox="0 0 30 12" className={size === "sm" ? "w-6" : "w-12"}>
          {[6, 13, 20, 26].map((x) => (
            <circle key={x} className="kc-bit" cx={x} cy={9} r={2} fill="var(--brand-accent)" />
          ))}
        </svg>
      )}
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
