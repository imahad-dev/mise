"use client";

import React, { useEffect, useRef, useState } from "react";
import { Button, Card } from "ui";
import { apiError } from "../lib/bill";
import { keepGiveKey, newGiveKey, payForwardText } from "../lib/floor";

/** Chai bought by guests for someone who needs it; "Give one" sends a free ticket to the kitchen. */
export function PayForwardTile({
  slug,
  balance,
  onChanged,
}: {
  slug: string | undefined;
  balance: number | null;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  // One key per intended give: a retry after a lost response must not hand out a second chai.
  const giveKey = useRef<string | null>(null);

  useEffect(() => {
    setMessage(null);
    giveKey.current = null;
  }, [slug]);

  const give = async () => {
    setBusy(true);
    setMessage(null);
    const key = (giveKey.current ??= newGiveKey());
    try {
      const res = await fetch(`/api/restaurants/${slug}/pay-forward/give`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantity: 1, idempotency_key: key }),
      });
      if (!keepGiveKey(res.status)) giveKey.current = null;
      setMessage(res.ok ? { text: "Given — the kitchen has the ticket.", error: false } : { text: await apiError(res), error: true });
    } catch {
      setMessage({ text: "Network error. Try again.", error: true });
    } finally {
      setBusy(false);
      onChanged();
    }
  };

  if (balance === null) return null;
  return (
    <Card className="flex flex-wrap items-center gap-3 p-4">
      <span className="font-semibold">{payForwardText(balance)}</span>
      <Button className="ml-auto" disabled={busy || balance < 1} onClick={give}>
        Give one
      </Button>
      {message && (
        <p role={message.error ? "alert" : "status"} className={`w-full text-sm ${message.error ? "text-danger-fg" : "text-ink-muted"}`}>
          {message.text}
        </p>
      )}
    </Card>
  );
}
