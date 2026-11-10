"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** Coals glow under the mark, then the name rises. About 2 s; the still logo under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".ah-coal", { opacity: 0, scale: 0.3, transformOrigin: "50% 50%", stagger: 0.08, duration: 0.35 })
          .to(".ah-coal", { fill: "#ff9a3d", duration: 0.4 }, "<0.2")
          .from(".ah-mark", { opacity: 0, y: 12, duration: 0.45 }, "-=0.2")
          .from(".ah-name", { opacity: 0, y: 24, duration: 0.5 }, "-=0.1")
          .to({}, { duration: 0.4 });
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
    <div ref={root} className="flex flex-col items-center gap-4 text-[var(--brand-on-deep)]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="ah-mark h-28 w-28" src="/venues/angeethi-house/mark.svg" alt="" />
      <svg aria-hidden="true" viewBox="0 0 120 16" className="h-4 w-40">
        {[10, 30, 50, 70, 90, 110].map((x) => (
          <circle key={x} className="ah-coal" cx={x} cy={8} r={6} fill="#5e0016" />
        ))}
      </svg>
      <p className="ah-name font-serif text-4xl uppercase tracking-wide">{name}</p>
    </div>
  );
}
