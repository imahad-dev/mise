"use client";

import React, { useEffect, useRef } from "react";
import { getDictionary } from "../i18n";
import { typeDigits } from "../lib/ordering";

export interface CodeEntryProps {
  lang: string;
  code: string;
  onChange: (code: string) => void;
  /** A plain sentence under the boxes (wrong number, too many tries). */
  message: string | null;
  /** Seconds left before the boxes can be used again, or 0. */
  lockedFor: number;
  busy: boolean;
}

/** Four large boxes for the table's 4-digit number; the parent sends once all four are filled. */
export function CodeEntry({ lang, code, onChange, message, lockedFor, busy }: CodeEntryProps) {
  const dict = getDictionary(lang);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  const disabled = busy || lockedFor > 0;

  // Keep the cursor on the first empty box (also after the boxes are cleared); after a tick,
  // because opening the sheet's dialog moves focus to its close button.
  useEffect(() => {
    if (disabled) return;
    const t = setTimeout(() => boxes.current[Math.min(code.length, 3)]?.focus(), 0);
    return () => clearTimeout(t);
  }, [code, disabled]);

  return (
    <div className="space-y-4">
      <p className="text-base text-ink">{dict.order.numberHelp}</p>
      <div className="flex justify-center gap-3">
        {[0, 1, 2, 3].map((i) => (
          <input
            key={i}
            ref={(el) => {
              boxes.current[i] = el;
            }}
            value={code[i] ?? ""}
            onChange={(e) => onChange(typeDigits(code, i, e.target.value))}
            onKeyDown={(e) => {
              if (e.key === "Backspace" && !code[i] && i > 0) onChange(code.slice(0, i - 1));
            }}
            onFocus={(e) => e.target.select()}
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete={i === 0 ? "one-time-code" : "off"}
            aria-label={dict.order.numberDigit.replace("{n}", String(i + 1))}
            disabled={disabled}
            className="h-16 w-14 rounded-xl border-2 border-line bg-card text-center text-3xl font-semibold tabular-nums text-ink focus:border-terracotta focus:outline-none disabled:opacity-50"
          />
        ))}
      </div>
      {message && (
        <p role="alert" className="text-base text-danger-fg">
          {message}
        </p>
      )}
      {lockedFor > 0 && (
        <p className="text-base tabular-nums text-ink-muted">
          {dict.order.tryAgainIn.replace("{seconds}", String(lockedFor))}
        </p>
      )}
    </div>
  );
}
