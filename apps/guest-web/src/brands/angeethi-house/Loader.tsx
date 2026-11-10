"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** Three embers pulse in turn; still under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".ah-ember", { opacity: 1, scale: 1.25, transformOrigin: "50% 50%", duration: 0.35, stagger: 0.18, repeat: -1, yoyo: true });
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      <svg aria-hidden="true" viewBox="0 0 30 10" className={size === "sm" ? "w-6" : "w-12"}>
        {[5, 15, 25].map((x) => (
          <circle key={x} className="ah-ember" cx={x} cy={5} r={3} fill="var(--brand-spark)" opacity={0.45} />
        ))}
      </svg>
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
