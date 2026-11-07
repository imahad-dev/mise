"use client";

import React, { createContext, useContext, useRef, useState } from "react";
import { Button } from "ui";

export const ALLERGENS = [
  "gluten", "milk", "eggs", "fish", "crustaceans", "molluscs", "tree_nuts", "peanuts", "soy",
  "celery", "mustard", "sesame", "sulphites", "lupin",
];

export interface OwnerChoice {
  id: string;
  label: string;
  price_delta: string;
  cost_delta: string;
  allergens: string[];
  allergen_verified: boolean;
  is_vegetarian: boolean;
  is_vegan: boolean;
  available: boolean;
  is_default: boolean;
  sort_order: number;
}

export interface OwnerChoiceGroup {
  id: string;
  label: string;
  kind: "pick" | "add" | "leave_out";
  min_select: number;
  max_select: number;
  sort_order: number;
  choices: OwnerChoice[];
}

const KINDS = { pick: "Pick one", add: "Add extras", leave_out: "Leave out" } as const;
const PRESET = {
  pick: { min_select: 1, max_select: 1 },
  add: { min_select: 0, max_select: 3 },
  leave_out: { min_select: 0, max_select: 5 },
};

// True while a save is in flight; controls say so but stay focusable (no focus jump).
const Busy = createContext(false);

type Req = [path: string, method: string, body?: unknown];
type Send = (reqs: Req[]) => Promise<boolean>;

interface Props {
  slug: string;
  itemId: string;
  groups: OwnerChoiceGroup[];
  money: (n: number) => string;
  onChanged: () => void | Promise<void>;
}

// The server words its refusals for the owner; show them as they come.
function serverMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  const first = Array.isArray(detail) ? detail[0] : null;
  if (first && typeof first.msg === "string") return first.msg.replace(/^Value error, /, "");
  return "That change wasn't saved. Check the details and try again.";
}

/** Renumber every sibling 0..n-1 in the new order, so tied or gapped positions can't misorder. */
function moveRequests(base: string, ids: string[], i: number, by: number): Req[] {
  const order = [...ids];
  [order[i], order[i + by]] = [order[i + by], order[i]];
  return order.map((id, n): Req => [`${base}/${id}`, "PATCH", { sort_order: n }]);
}

const input = "mt-1 block rounded-lg border border-line bg-card p-2 text-sm text-ink";

export function ChoiceEditor({ slug, itemId, groups, money, onChanged }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<keyof typeof KINDS>("pick");
  const api = `/api/restaurants/${slug}`;

  // One save at a time: the editor stays locked until the list has reloaded, so a
  // second tick never builds on a stale list and a double click sends once.
  const send: Send = async (reqs) => {
    if (busyRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    let done = 0;
    try {
      for (const [path, method, body] of reqs) {
        const res = await fetch(`${api}${path}`, {
          method,
          headers: { "Content-Type": "application/json" },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
        if (!res.ok) {
          setError(serverMessage((await res.json().catch(() => null))?.detail));
          break;
        }
        done += 1;
      }
      if (done === reqs.length) setError(null);
      if (done > 0) await onChanged();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
    return done === reqs.length;
  };

  const focusGroup = (id: string) => document.getElementById(`choice-group-${id}`)?.focus();
  const groupIds = groups.map((x) => x.id);

  return (
    <div className="space-y-3 border-t border-line pt-3" aria-busy={busy}>
      <h4 ref={headingRef} tabIndex={-1} className="text-sm font-semibold text-ink">Choices</h4>
      {error && <p role="alert" className="text-sm text-danger-fg">{error}</p>}
      <Busy.Provider value={busy}>
      <div className="space-y-3">
        {groups.map((g, i) => (
          <div key={g.id} className="space-y-2 rounded-xl bg-paper-2 p-3">
            <div className="flex items-center justify-between gap-2 text-sm font-semibold text-ink">
              <span id={`choice-group-${g.id}`} tabIndex={-1}>
                {g.label} · {KINDS[g.kind]} · {g.min_select > 0 ? "required" : "optional"}, up to {g.max_select}
              </span>
              <span className="flex gap-1">
                <Button aria-disabled={busy} variant="outline" size="icon" aria-label={`Move ${g.label} up`} disabled={i === 0} onClick={() => void send(moveRequests("/choice-groups", groupIds, i, -1))}>↑</Button>
                <Button aria-disabled={busy} variant="outline" size="icon" aria-label={`Move ${g.label} down`} disabled={i === groups.length - 1} onClick={() => void send(moveRequests("/choice-groups", groupIds, i, 1))}>↓</Button>
                <Button
                  aria-disabled={busy}
                  variant="outline"
                  aria-label={`Delete ${g.label}`}
                  onClick={() => void send([[`/choice-groups/${g.id}`, "DELETE"]]).then((ok) => ok && headingRef.current?.focus())}
                >
                  Delete
                </Button>
              </span>
            </div>
            {g.choices.filter((c) => c.available).length < g.min_select && (
              <p className="text-xs text-danger-fg">Guests can&apos;t order this dish until this group has a choice.</p>
            )}
            <GroupEdit key={`${g.label}|${g.min_select}|${g.max_select}`} group={g} send={send} />
            <ul className="space-y-2">
              {g.choices.map((c, ci) => (
                <ChoiceRow
                  key={c.id}
                  choice={c}
                  kind={g.kind}
                  money={money}
                  send={send}
                  first={ci === 0}
                  last={ci === g.choices.length - 1}
                  move={(by) => send(moveRequests("/choices", g.choices.map((x) => x.id), ci, by))}
                  afterDelete={() => focusGroup(g.id)}
                />
              ))}
            </ul>
            <NewChoice group={g} send={send} />
          </div>
        ))}
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            // No sort_order: the server puts a new group last.
            void send([[`/menu-items/${itemId}/choice-groups`, "POST", { label, kind, ...PRESET[kind] }]]).then((ok) => ok && setLabel(""));
          }}
        >
          <label className="text-xs text-ink-muted">
            New group
            <input aria-disabled={busy} required value={label} onChange={(e) => setLabel(e.target.value)} className={input} />
          </label>
          <label className="text-xs text-ink-muted">
            Type
            <select aria-disabled={busy} value={kind} onChange={(e) => setKind(e.target.value as keyof typeof KINDS)} className={input}>
              {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <Button aria-disabled={busy} type="submit" variant="outline">Add group</Button>
        </form>
      </div>
      </Busy.Provider>
    </div>
  );
}

function GroupEdit({ group: g, send }: { group: OwnerChoiceGroup; send: Send }) {
  const busy = useContext(Busy);
  const [label, setLabel] = useState(g.label);
  const [min, setMin] = useState(String(g.min_select));
  const [max, setMax] = useState(String(g.max_select));
  const num = `${input} w-20`;
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        void send([[`/choice-groups/${g.id}`, "PATCH", { label, min_select: Number(min), max_select: Number(max) }]]);
      }}
    >
      <label className="text-xs text-ink-muted">
        Group name
        <input aria-disabled={busy} required aria-label={`Name of ${g.label}`} value={label} onChange={(e) => setLabel(e.target.value)} className={input} />
      </label>
      <label className="text-xs text-ink-muted">
        At least
        <input aria-disabled={busy} type="number" min="0" max="20" aria-label={`At least, ${g.label}`} value={min} onChange={(e) => setMin(e.target.value)} className={num} />
      </label>
      <label className="text-xs text-ink-muted">
        At most
        <input aria-disabled={busy} type="number" min="1" max="20" aria-label={`At most, ${g.label}`} value={max} onChange={(e) => setMax(e.target.value)} className={num} />
      </label>
      <Button aria-disabled={busy} type="submit" variant="outline" aria-label={`Save ${g.label}`}>Save</Button>
    </form>
  );
}

function ChoiceRow({
  choice: c, kind, money, send, first, last, move, afterDelete,
}: {
  choice: OwnerChoice;
  kind: OwnerChoiceGroup["kind"];
  money: (n: number) => string;
  send: Send;
  first: boolean;
  last: boolean;
  move: (by: number) => Promise<boolean>;
  afterDelete: () => void;
}) {
  const busy = useContext(Busy);
  const patch = (body: object) => void send([[`/choices/${c.id}`, "PATCH", body]]);
  const toggleAllergen = (a: string) =>
    patch({ allergens: c.allergens.includes(a) ? c.allergens.filter((x) => x !== a) : [...c.allergens, a] });
  const leaveOut = kind === "leave_out";
  return (
    <li className="space-y-1 text-sm text-ink">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {c.label}
          {Number(c.price_delta) > 0 && <span className="tabular-nums"> +{money(Number(c.price_delta))}</span>}
          {!leaveOut && <span className="tabular-nums text-xs font-normal text-ink-muted"> · cost {money(Number(c.cost_delta))}</span>}
        </span>
        <span className="flex flex-wrap items-center gap-3 text-xs">
          <Button aria-disabled={busy} variant="outline" size="icon" aria-label={`Move ${c.label} up`} disabled={first} onClick={() => void move(-1)}>↑</Button>
          <Button aria-disabled={busy} variant="outline" size="icon" aria-label={`Move ${c.label} down`} disabled={last} onClick={() => void move(1)}>↓</Button>
          <label className="flex items-center gap-1">
            <input aria-disabled={busy} type="checkbox" aria-label={`On sale: ${c.label}`} checked={c.available} onChange={(e) => patch({ available: e.target.checked })} /> On sale
          </label>
          <label className="flex items-center gap-1">
            <input aria-disabled={busy} type="checkbox" aria-label={`Starts selected: ${c.label}`} checked={c.is_default} onChange={(e) => patch({ is_default: e.target.checked })} /> Starts selected
          </label>
          <button
            aria-disabled={busy}
            type="button"
            className="underline"
            aria-label={`Delete ${c.label}`}
            onClick={() => void send([[`/choices/${c.id}`, "DELETE"]]).then((ok) => ok && afterDelete())}
          >
            Delete
          </button>
        </span>
      </div>
      <ChoiceEdit key={`${c.label}|${c.price_delta}|${c.cost_delta}`} choice={c} leaveOut={leaveOut} send={send} />
      {leaveOut ? (
        <p className="text-xs text-ink-muted">Leave-outs need no allergen check</p>
      ) : (
        <details className="text-xs">
          <summary className="cursor-pointer">
            Allergens: {c.allergens.join(", ") || "none"} · {c.allergen_verified ? "Confirmed" : "Unconfirmed"}
          </summary>
          <div className="mt-1 flex flex-wrap gap-2">
            {ALLERGENS.map((a) => (
              <label key={a} className="flex items-center gap-1">
                <input aria-disabled={busy} type="checkbox" aria-label={`${a} in ${c.label}`} checked={c.allergens.includes(a)} onChange={() => toggleAllergen(a)} /> {a}
              </label>
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-3">
            <label className="flex items-center gap-1">
              <input aria-disabled={busy} type="checkbox" aria-label={`Allergens confirmed for ${c.label}`} checked={c.allergen_verified} onChange={(e) => patch({ allergen_verified: e.target.checked })} /> Allergens confirmed
            </label>
            <label className="flex items-center gap-1">
              <input aria-disabled={busy} type="checkbox" aria-label={`Vegetarian: ${c.label}`} checked={c.is_vegetarian} onChange={(e) => patch({ is_vegetarian: e.target.checked })} /> Vegetarian
            </label>
            <label className="flex items-center gap-1">
              <input aria-disabled={busy} type="checkbox" aria-label={`Vegan: ${c.label}`} checked={c.is_vegan} onChange={(e) => patch({ is_vegan: e.target.checked })} /> Vegan
            </label>
          </div>
        </details>
      )}
    </li>
  );
}

function ChoiceEdit({ choice: c, leaveOut, send }: { choice: OwnerChoice; leaveOut: boolean; send: Send }) {
  const busy = useContext(Busy);
  const [label, setLabel] = useState(c.label);
  const [price, setPrice] = useState(c.price_delta);
  const [cost, setCost] = useState(c.cost_delta);
  const num = `${input} w-24`;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer">Edit {c.label}</summary>
      <form
        className="mt-1 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send([[`/choices/${c.id}`, "PATCH", leaveOut ? { label } : { label, price_delta: price, cost_delta: cost }]]);
        }}
      >
        <label className="text-ink-muted">
          Name
          <input aria-disabled={busy} required aria-label={`Name of ${c.label}`} value={label} onChange={(e) => setLabel(e.target.value)} className={input} />
        </label>
        {!leaveOut && (
          <>
            <label className="text-ink-muted">
              Price
              <input aria-disabled={busy} type="number" min="0" step="0.01" aria-label={`Price of ${c.label}`} value={price} onChange={(e) => setPrice(e.target.value)} className={num} />
            </label>
            <label className="text-ink-muted">
              Cost
              <input aria-disabled={busy} type="number" min="0" step="0.01" aria-label={`Cost of ${c.label}`} value={cost} onChange={(e) => setCost(e.target.value)} className={num} />
            </label>
          </>
        )}
        <Button aria-disabled={busy} type="submit" variant="outline" aria-label={`Save ${c.label}`}>Save</Button>
      </form>
    </details>
  );
}

function NewChoice({ group: g, send }: { group: OwnerChoiceGroup; send: Send }) {
  const busy = useContext(Busy);
  const [label, setLabel] = useState("");
  const [price, setPrice] = useState("0");
  const [cost, setCost] = useState("0");
  const leaveOut = g.kind === "leave_out";
  const num = `${input} w-24`;
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const amounts = leaveOut ? {} : { price_delta: price, cost_delta: cost };
        // No sort_order: the server puts a new choice last.
        void send([[`/choice-groups/${g.id}/choices`, "POST", { label, ...amounts }]]).then((ok) => ok && setLabel(""));
      }}
    >
      <label className="text-xs text-ink-muted">
        New choice
        <input aria-disabled={busy} required aria-label={`New choice name for ${g.label}`} value={label} onChange={(e) => setLabel(e.target.value)} className={`${input} w-40`} />
      </label>
      {!leaveOut && (
        <>
          <label className="text-xs text-ink-muted">
            Price
            <input aria-disabled={busy} type="number" min="0" step="0.01" aria-label={`New choice price for ${g.label}`} value={price} onChange={(e) => setPrice(e.target.value)} className={num} />
          </label>
          <label className="text-xs text-ink-muted">
            Cost
            <input aria-disabled={busy} type="number" min="0" step="0.01" aria-label={`New choice cost for ${g.label}`} value={cost} onChange={(e) => setCost(e.target.value)} className={num} />
          </label>
        </>
      )}
      <Button aria-disabled={busy} type="submit" variant="outline" aria-label={`Add choice to ${g.label}`}>Add</Button>
    </form>
  );
}
