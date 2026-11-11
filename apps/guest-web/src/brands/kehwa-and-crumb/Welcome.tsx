"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** A cup fills with kehwa, crumbs settle, then the name and the mark. About 2 s; the mark shows still under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".kc-tea", { scaleY: 0, transformOrigin: "50% 100%", duration: 0.7, ease: "power2.out" })
          .from(".kc-crumb", { y: -40, opacity: 0, stagger: 0.07, duration: 0.45, ease: "bounce.out" }, "-=0.2")
          .from(".kc-name", { opacity: 0, y: 16, duration: 0.45 }, "-=0.1")
          .from(".kc-mark", { opacity: 0, scale: 0.8, duration: 0.4, ease: "power2.out" }, "-=0.1")
          .to({}, { duration: 0.2 });
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
      <svg aria-hidden="true" viewBox="0 0 80 70" className="h-24 w-28">
        <path d="M10 18h50v22a25 25 0 0 1-50 0z" fill="none" stroke="var(--brand-on-deep)" strokeWidth="3" />
        <path d="M60 24h6a8 8 0 0 1 0 16h-6" fill="none" stroke="var(--brand-on-deep)" strokeWidth="3" />
        <path className="kc-tea" d="M13 24h44v16a22 22 0 0 1-44 0z" fill="var(--brand-spark)" />
        {[22, 33, 44, 51].map((x, i) => (
          <circle key={x} className="kc-crumb" cx={x} cy={i % 2 ? 66 : 64} r={2} fill="var(--brand-on-deep)" />
        ))}
      </svg>
      {/* eslint-disable-next-line @next/next/no-img-element -- a small static mark */}
      <img className="kc-mark h-14 w-14 rounded-xl" src="/venues/kehwa-and-crumb/mark.svg" alt="" />
      <p className="kc-name font-serif text-4xl">{name}</p>
    </div>
  );
}
