"use client";

import React, { useState } from "react";
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

type Send = (path: string, method: string, body?: unknown) => Promise<boolean>;

interface Props {
  slug: string;
  itemId: string;
  groups: OwnerChoiceGroup[];
  money: (n: number) => string;
  onChanged: () => void;
}

// The server words its refusals for the owner; show them as they come.
function serverMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  const first = Array.isArray(detail) ? detail[0] : null;
  if (first && typeof first.msg === "string") return first.msg.replace(/^Value error, /, "");
  return "That change wasn't saved. Check the details and try again.";
}

export function ChoiceEditor({ slug, itemId, groups, money, onChanged }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<keyof typeof KINDS>("pick");
  const base = `/api/restaurants/${slug}`;

  const send: Send = async (path, method, body) => {
    setError(null);
    const res = await fetch(`${base}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      setError(serverMessage((await res.json().catch(() => null))?.detail));
      return false;
    }
    onChanged();
    return true;
  };

  // Swap positions: a neighbour's sort_order may equal this one's after seeding or adding.
  const moveGroup = async (i: number, by: number) => {
    const other = groups[i + by];
    if (!other) return;
    if (await send(`/choice-groups/${groups[i].id}`, "PATCH", { sort_order: i + by })) {
      await send(`/choice-groups/${other.id}`, "PATCH", { sort_order: i });
    }
  };

  return (
    <div className="space-y-3 border-t border-line pt-3">
      <h4 className="text-sm font-semibold text-ink">Choices</h4>
      {error && <p role="alert" className="text-sm text-danger-fg">{error}</p>}
      {groups.map((g, i) => (
        <div key={g.id} className="space-y-2 rounded-xl bg-paper-2 p-3">
          <div className="flex items-center justify-between gap-2 text-sm font-semibold text-ink">
            <span>
              {g.label} · {KINDS[g.kind]} · {g.min_select > 0 ? "required" : "optional"}, up to {g.max_select}
            </span>
            <span className="flex gap-1">
              <Button variant="outline" size="icon" aria-label={`Move ${g.label} up`} onClick={() => void moveGroup(i, -1)}>↑</Button>
              <Button variant="outline" size="icon" aria-label={`Move ${g.label} down`} onClick={() => void moveGroup(i, 1)}>↓</Button>
              <Button variant="outline" aria-label={`Delete ${g.label}`} onClick={() => void send(`/choice-groups/${g.id}`, "DELETE")}>Delete</Button>
            </span>
          </div>
          <ul className="space-y-2">
            {g.choices.map((c) => (
              <ChoiceRow key={c.id} choice={c} kind={g.kind} money={money} send={send} />
            ))}
          </ul>
          <NewChoice groupId={g.id} kind={g.kind} send={send} />
        </div>
      ))}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(`/menu-items/${itemId}/choice-groups`, "POST", {
            label,
            kind,
            ...PRESET[kind],
            sort_order: groups.length,
          }).then((ok) => ok && setLabel(""));
        }}
      >
        <label className="text-xs text-ink-muted">
          New group
          <input required value={label} onChange={(e) => setLabel(e.target.value)} className="mt-1 block rounded-lg border border-line bg-card p-2 text-sm text-ink" />
        </label>
        <label className="text-xs text-ink-muted">
          Type
          <select value={kind} onChange={(e) => setKind(e.target.value as keyof typeof KINDS)} className="mt-1 block rounded-lg border border-line bg-card p-2 text-sm text-ink">
            {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <Button type="submit" variant="outline">Add group</Button>
      </form>
    </div>
  );
}

function ChoiceRow({
  choice: c, kind, money, send,
}: {
  choice: OwnerChoice;
  kind: OwnerChoiceGroup["kind"];
  money: (n: number) => string;
  send: Send;
}) {
  const patch = (body: object) => void send(`/choices/${c.id}`, "PATCH", body);
  const toggleAllergen = (a: string) =>
    patch({ allergens: c.allergens.includes(a) ? c.allergens.filter((x) => x !== a) : [...c.allergens, a] });
  return (
    <li className="space-y-1 text-sm text-ink">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {c.label}
          {Number(c.price_delta) > 0 && <span className="tabular-nums"> +{money(Number(c.price_delta))}</span>}
        </span>
        <span className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={c.available} onChange={(e) => patch({ available: e.target.checked })} /> On sale
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={c.is_default} onChange={(e) => patch({ is_default: e.target.checked })} /> Starts selected
          </label>
          <button type="button" className="underline" onClick={() => void send(`/choices/${c.id}`, "DELETE")}>Delete</button>
        </span>
      </div>
      {kind === "leave_out" ? (
        <p className="text-xs text-ink-muted">Leave-outs need no allergen check</p>
      ) : (
        <details className="text-xs">
          <summary className="cursor-pointer">
            Allergens: {c.allergens.join(", ") || "none"} · {c.allergen_verified ? "Confirmed" : "Unconfirmed"}
          </summary>
          <div className="mt-1 flex flex-wrap gap-2">
            {ALLERGENS.map((a) => (
              <label key={a} className="flex items-center gap-1">
                <input type="checkbox" checked={c.allergens.includes(a)} onChange={() => toggleAllergen(a)} /> {a}
              </label>
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-3">
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={c.allergen_verified} onChange={(e) => patch({ allergen_verified: e.target.checked })} /> Allergens confirmed
            </label>
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={c.is_vegetarian} onChange={(e) => patch({ is_vegetarian: e.target.checked })} /> Vegetarian
            </label>
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={c.is_vegan} onChange={(e) => patch({ is_vegan: e.target.checked })} /> Vegan
            </label>
          </div>
        </details>
      )}
    </li>
  );
}

function NewChoice({ groupId, kind, send }: { groupId: string; kind: OwnerChoiceGroup["kind"]; send: Send }) {
  const [label, setLabel] = useState("");
  const [price, setPrice] = useState("0");
  const [cost, setCost] = useState("0");
  const field = "mt-1 block w-24 rounded-lg border border-line bg-card p-2 text-sm text-ink";
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const amounts = kind === "leave_out" ? {} : { price_delta: price, cost_delta: cost };
        void send(`/choice-groups/${groupId}/choices`, "POST", { label, ...amounts }).then((ok) => ok && setLabel(""));
      }}
    >
      <label className="text-xs text-ink-muted">
        New choice
        <input required value={label} onChange={(e) => setLabel(e.target.value)} className={`${field} w-40`} />
      </label>
      {kind !== "leave_out" && (
        <>
          <label className="text-xs text-ink-muted">
            Price
            <input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} className={field} />
          </label>
          <label className="text-xs text-ink-muted">
            Cost
            <input type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} className={field} />
          </label>
        </>
      )}
      <Button type="submit" variant="outline">Add</Button>
    </form>
  );
}
