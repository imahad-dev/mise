"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** Crumbs fall and gather; still under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
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
      <svg aria-hidden="true" viewBox="0 0 30 12" className={size === "sm" ? "w-6" : "w-12"}>
        {[6, 13, 20, 26].map((x) => (
          <circle key={x} className="kc-bit" cx={x} cy={9} r={2} fill="var(--brand-accent)" />
        ))}
      </svg>
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
