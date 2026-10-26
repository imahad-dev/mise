"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Button, Sheet } from "ui";
import { getDictionary } from "../i18n";

/** Mirrors ServiceCallResponse in services/api/src/schemas/floor.py. */
export interface ServiceCall {
  id: string;
  reason: string;
  reason_label: string;
  created_at: string;
  resolved_at: string | null;
}

const REASONS = ["help", "water", "extra"] as const;

export type CallOutcome = "called" | "already" | "unavailable" | "failed" | { wait: number };

/** What a POST /api/guest/service-calls status means for the guest. */
export function callOutcome(status: number, retryAfter: string | null): CallOutcome {
  if (status === 201) return "called";
  if (status === 409) return "already";
  if (status === 422) return "unavailable"; // counter or no-table session: no waiter to call
  if (status === 429) {
    const seconds = Math.ceil(Number(retryAfter));
    return { wait: Number.isFinite(seconds) && seconds > 0 ? seconds : 60 };
  }
  return "failed";
}

export const formatElapsed = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/** "Call waiter" for table sessions; render it only when the menu says table_kind === "table". */
export function CallWaiter({ lang, extraLabel }: { lang: string; extraLabel: string | null }) {
  const dict = getDictionary(lang);
  const [call, setCall] = useState<ServiceCall | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const loadCurrent = useCallback(async () => {
    try {
      const r = await fetch("/api/guest/service-calls/current");
      if (r.ok) setCall(((await r.json()) as { call: ServiceCall | null }).call);
    } catch {
      // keep the last known call; the next poll retries
    }
  }, []);

  useEffect(() => {
    void loadCurrent(); // after a reload the open call (and its timer) comes back from the server
  }, [loadCurrent]);

  const callOpen = call !== null;
  useEffect(() => {
    if (!callOpen) return;
    const poll = setInterval(() => void loadCurrent(), 15_000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [callOpen, loadCurrent]);

  const send = async (reason: (typeof REASONS)[number]) => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await fetch("/api/guest/service-calls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      const outcome = callOutcome(r.status, r.headers.get("Retry-After"));
      if (outcome === "called") {
        setCall((await r.json()) as ServiceCall);
        setNow(Date.now());
        setOpen(false);
      } else if (outcome === "already") {
        setMessage(dict.call.already);
        void loadCurrent();
      } else if (outcome === "unavailable") {
        setOpen(false);
        setHidden(true);
      } else if (outcome === "failed") {
        setMessage(dict.call.failed);
      } else {
        setMessage(dict.call.wait.replace("{seconds}", String(outcome.wait)));
      }
    } catch {
      setMessage(dict.call.failed);
    } finally {
      setBusy(false);
    }
  };

  if (hidden) return null;

  if (call) {
    // shortcut: elapsed uses the guest's clock against the server's created_at, so a skewed phone clock
    // skews this timer; staff timers use the server offset. Upgrade by returning server_time from /current.
    return (
      <span role="status" className="btn-ghost pointer-events-none whitespace-nowrap tabular-nums">
        {dict.call.called.replace("{time}", formatElapsed(now - Date.parse(call.created_at)))}
      </span>
    );
  }

  const labels = { help: dict.call.help, water: dict.call.water, extra: extraLabel || dict.call.extra };
  return (
    <>
      <Button
        variant="outline"
        className="whitespace-nowrap"
        onClick={() => {
          setMessage(null);
          setOpen(true);
        }}
      >
        {dict.call.button}
      </Button>
      <Sheet open={open} onClose={() => setOpen(false)} title={dict.call.button}>
        <div className="space-y-2">
          {REASONS.map((reason) => (
            <Button key={reason} className="w-full" disabled={busy} onClick={() => send(reason)}>
              {labels[reason]}
            </Button>
          ))}
          {message && (
            <p role="alert" className="text-sm text-ink">
              {message}
            </p>
          )}
        </div>
      </Sheet>
    </>
  );
}
