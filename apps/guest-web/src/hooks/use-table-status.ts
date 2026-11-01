"use client";

import { useCallback, useEffect, useState } from "react";
import { nextStatusCheck, type GuestStatus } from "../lib/ordering";

const TIMEOUT_MS = 8000;

/**
 * This phone's table status. Checks once, then again after each answer while the table is waiting
 * (nextStatusCheck), never while the page is hidden. `reload` starts a fresh round.
 */
export function useTableStatus() {
  const [status, setStatus] = useState<GuestStatus | null>(null);
  const [round, setRound] = useState(0);
  const reload = useCallback(() => setRound((n) => n + 1), []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ctrl: AbortController | undefined;
    let failures = 0;
    let stopped = false;

    const check = async () => {
      timer = undefined;
      if (document.visibilityState === "hidden") return; // resumed by `visible`
      ctrl = new AbortController();
      const abort = setTimeout(() => ctrl?.abort(), TIMEOUT_MS);
      let state: GuestStatus["table_state"] | undefined;
      let signedOut = false;
      try {
        const res = await fetch("/api/guest/session", { signal: ctrl.signal });
        if (res.ok) {
          const next = (await res.json()) as GuestStatus;
          if (stopped) return;
          setStatus(next);
          state = next.table_state;
          failures = 0;
        } else {
          signedOut = res.status === 401;
          failures += 1;
        }
      } catch {
        failures += 1; // network blip or timeout
      } finally {
        clearTimeout(abort);
        ctrl = undefined;
      }
      if (stopped) return;
      const wait = nextStatusCheck({ state, failures, signedOut });
      if (wait === null) stopped = true;
      else timer = setTimeout(check, wait);
    };

    const visible = () => {
      if (document.visibilityState === "visible" && !stopped && !timer && !ctrl) void check();
    };
    void check();
    document.addEventListener("visibilitychange", visible);
    return () => {
      stopped = true;
      clearTimeout(timer);
      ctrl?.abort();
      document.removeEventListener("visibilitychange", visible);
    };
  }, [round]);

  return { status, reload };
}
