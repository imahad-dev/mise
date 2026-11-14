"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { SKEWER_LONG } from "./logo";

gsap.registerPlugin(useGSAP);

/** The lockup's skewer shoots in, the mark stamps down on it like a shop sign, then the name. About 2 s; still under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".tt-skewer", { xPercent: -140, duration: 0.5, ease: "power4.out" })
          .from(".tt-mark", { scale: 1.9, rotate: -10, opacity: 0, duration: 0.24, ease: "power4.in" }, "+=0.05")
          .to(".tt-sign", { y: 5, duration: 0.06, yoyo: true, repeat: 1, ease: "power1.out" })
          .from(".tt-name", { opacity: 0, y: 18, duration: 0.4, ease: "power3.out" }, "-=0.02")
          .to({}, { duration: 0.55 });
      });
      mm.add("(prefers-reduced-motion: reduce)", () => {
        // Plain timer, not GSAP: nothing animates here, and it stays testable with fake timers.
        const t = setTimeout(onDone, 1200);
        return () => clearTimeout(t);
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <div ref={root} className="flex flex-col items-center gap-4 overflow-hidden text-[var(--brand-on-deep)]">
      <div className="tt-sign flex flex-col items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element -- a small static mark */}
        <img className="tt-mark h-28 w-28 rounded-sm" src="/venues/tikka-town/mark.svg" alt="" />
        <svg aria-hidden="true" viewBox="14 70 706 44" className="tt-skewer h-5 w-64">
          <path d={SKEWER_LONG} fill="var(--brand-spark)" fillRule="evenodd" />
        </svg>
      </div>
      <p className="tt-name font-serif text-6xl uppercase leading-none tracking-wide">{name}</p>
    </div>
  );
}
