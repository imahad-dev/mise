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

/** Three embers pulse in turn; the venue's still mark under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
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
      {reduced ? (
        {/* eslint-disable-next-line @next/next/no-img-element -- a small static mark */}
        <img src="/venues/angeethi-house/mark.svg" alt="" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"} />
      ) : (
        <svg aria-hidden="true" viewBox="0 0 30 10" className={size === "sm" ? "w-6" : "w-12"}>
          {[5, 15, 25].map((x) => (
            <circle key={x} className="ah-ember" cx={x} cy={5} r={3} fill="var(--brand-spark)" opacity={0.45} />
          ))}
        </svg>
      )}
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
