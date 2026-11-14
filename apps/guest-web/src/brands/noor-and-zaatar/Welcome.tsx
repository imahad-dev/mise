"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { BOWL, FLAME } from "./logo";

gsap.registerPlugin(useGSAP);

/** The logo's lamp: the bowl rises, the flame catches and flickers, then the name. About 2 s; still under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".nz-bowl", { y: 40, opacity: 0, duration: 0.55, ease: "power3.out" })
          .from(".nz-flame", { scale: 0, transformOrigin: "50% 100%", duration: 0.45, ease: "back.out(3)" }, "-=0.1")
          .to(".nz-flame", { scaleY: 0.82, scaleX: 1.08, transformOrigin: "50% 100%", duration: 0.12, yoyo: true, repeat: 3, ease: "sine.inOut" })
          .from(".nz-name", { opacity: 0, y: 18, duration: 0.45 }, "-=0.35")
          .to({}, { duration: 0.35 });
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
    <div ref={root} className="flex flex-col items-center gap-5 text-[var(--brand-on-deep)]">
      <svg aria-hidden="true" viewBox="15 25 170 162" className="h-32 w-32 overflow-visible">
        <path className="nz-bowl" d={BOWL} fill="var(--brand-on-deep)" />
        <path className="nz-flame" d={FLAME} fill="var(--brand-spark)" />
      </svg>
      <p className="nz-name font-serif text-4xl">{name}</p>
    </div>
  );
}
