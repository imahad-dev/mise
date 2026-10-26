"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button, Sheet } from "ui";
import { getDictionary } from "../i18n";
import { VISIT_ENDED } from "../lib/pay";

/** Mirrors ServiceCallResponse in services/api/src/schemas/floor.py. */
export interface ServiceCall {
  id: string;
  reason: string;
  reason_label: string;
  created_at: string;
  resolved_at: string | null;
}

/** Mirrors CurrentCallResponse. */
interface CurrentCall {
  call: ServiceCall | null;
  available: boolean;
  extra_label: string | null;
  server_time: string;
}

const REASONS = ["help", "water", "extra"] as const;
type Reason = (typeof REASONS)[number];
const RESOLVED_MS = 10_000;

export type CallOutcome = "called" | "already" | "ended" | "unavailable" | "failed" | { wait: number };

/** What a POST /api/guest/service-calls status (and 409 detail) means for the guest. */
export function callOutcome(status: number, retryAfter: string | null, detail: unknown = null): CallOutcome {
  if (status === 201) return "called";
  if (status === 409) return detail === VISIT_ENDED ? "ended" : "already";
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

export interface CallWaiterViewProps {
  lang: string;
  extraLabel: string | null;
  /** Milliseconds the open call has waited, or null when there is no open call. */
  waitingMs: number | null;
  resolved: boolean;
  open: boolean;
  busy: boolean;
  message: string | null;
  onOpen: () => void;
  onClose: () => void;
  onSend: (reason: Reason) => void;
}

/** Stateless rendering, so it can be checked without a browser. */
export function CallWaiterView(p: CallWaiterViewProps) {
  const dict = getDictionary(p.lang);
  if (p.waitingMs !== null) {
    return (
      <span className="btn-ghost pointer-events-none whitespace-nowrap tabular-nums">
        <span role="status">{dict.call.called}</span>
        <span aria-hidden="true"> · {formatElapsed(p.waitingMs)}</span>
      </span>
    );
  }
  const labels = { help: dict.call.help, water: dict.call.water, extra: p.extraLabel || dict.call.extra };
  return (
    <>
      {p.resolved ? (
        <span role="status" className="text-sm text-ink">
          {dict.call.resolved}
        </span>
      ) : (
        <Button variant="outline" className="whitespace-nowrap" onClick={p.onOpen}>
          {dict.call.button}
        </Button>
      )}
      <Sheet open={p.open} onClose={p.onClose} title={dict.call.button}>
        <div className="space-y-2">
          {REASONS.map((reason) => (
            <Button key={reason} className="w-full" disabled={p.busy} onClick={() => p.onSend(reason)}>
              {labels[reason]}
            </Button>
          ))}
          {p.message && (
            <p role="alert" className="text-sm text-ink">
              {p.message}
            </p>
          )}
        </div>
      </Sheet>
    </>
  );
}

/** "Call waiter" for table sessions; hides itself unless the server says a waiter can be called. */
export function CallWaiter({ lang }: { lang: string }) {
  const dict = getDictionary(lang);
  const [current, setCurrent] = useState<CurrentCall | null>(null);
  const [loadedAt, setLoadedAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [resolved, setResolved] = useState(false);
  const lastCallId = useRef<string | null>(null);
  const resolvedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadCurrent = useCallback(async () => {
    try {
      const r = await fetch("/api/guest/service-calls/current");
      if (!r.ok) return; // keep the last known state; the next poll retries
      const body = (await r.json()) as CurrentCall;
      const at = Date.now();
      if (lastCallId.current && !body.call) {
        // staff resolved it: say so for a moment before offering the button again
        setResolved(true);
        if (resolvedTimer.current) clearTimeout(resolvedTimer.current);
        resolvedTimer.current = setTimeout(() => setResolved(false), RESOLVED_MS);
      }
      lastCallId.current = body.call?.id ?? null;
      setCurrent(body);
      setLoadedAt(at);
      setNow(at);
    } catch {
      // network blip: the next poll retries
    }
  }, []);

  useEffect(() => {
    void loadCurrent(); // after a reload the open call (and its timer) comes back from the server
    return () => {
      if (resolvedTimer.current) clearTimeout(resolvedTimer.current);
    };
  }, [loadCurrent]);

  const callOpen = Boolean(current?.call);
  useEffect(() => {
    if (!callOpen) return;
    const poll = setInterval(() => void loadCurrent(), 15_000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [callOpen, loadCurrent]);

  const send = async (reason: Reason) => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await fetch("/api/guest/service-calls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      const detail = r.status === 409 ? ((await r.json().catch(() => null)) as { detail?: unknown } | null)?.detail : null;
      const outcome = callOutcome(r.status, r.headers.get("Retry-After"), detail);
      if (outcome === "called") {
        setOpen(false);
        setResolved(false);
        await loadCurrent();
      } else if (outcome === "already") {
        setMessage(dict.call.already);
        void loadCurrent();
      } else if (outcome === "ended") {
        setMessage(dict.pay.visitEnded);
      } else if (outcome === "unavailable") {
        setOpen(false);
        setCurrent((c) => (c ? { ...c, available: false } : c));
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

  if (!current?.available) return null;
  const call = current.call;
  // Server clock at load plus client time since then: a skewed phone clock does not skew the timer.
  const waitingMs = call
    ? Date.parse(current.server_time) + (now - loadedAt) - Date.parse(call.created_at)
    : null;

  return (
    <CallWaiterView
      lang={lang}
      extraLabel={current.extra_label}
      waitingMs={waitingMs}
      resolved={resolved}
      open={open}
      busy={busy}
      message={message}
      onOpen={() => {
        setMessage(null);
        setOpen(true);
      }}
      onClose={() => setOpen(false)}
      onSend={send}
    />
  );
}
