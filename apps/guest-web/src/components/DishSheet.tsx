"use client";

import React, { useEffect, useRef, useState } from "react";
import { Badge, Button, Sheet } from "ui";
import { AllergenChip } from "./allergen-chip";
import type { TranslationDict } from "../i18n/types";
import {
  defaultPicks, firstMissing, isRadio, matchedAllergens, pickedChoices, requirement, toggle, unitPrice, worstStatus,
  type AllergenStatus, type CartChoice, type ChoiceGroup,
} from "../lib/choices";

export interface DishSheetItem {
  id: string;
  name: string;
  description?: string | null;
  price: string | number;
  image_url?: string | null;
  allergen_status: AllergenStatus;
  matched_allergens?: string[];
  options?: { id: string; label: string; price: string }[];
  choice_groups?: ChoiceGroup[];
}

export interface DishSheetProps {
  item: DishSheetItem;
  lang: string;
  dict: TranslationDict;
  formatPrice: (n: number) => string;
  /** The guest's dietary preferences, so a choice that doesn't fit can say so. */
  dietary: string[];
  onClose: () => void;
  onAdd: (
    option: { id: string; label: string; price: number } | undefined,
    choices: CartChoice[],
    quantity: number,
    status: AllergenStatus,
    matched: string[],
  ) => void;
}

/** The dish page: size, choices, quantity and a live total. Render with `key={dish.id}`. */
export function DishSheet({ item, lang, dict, formatPrice, dietary, onClose, onAdd }: DishSheetProps) {
  const groups = item.choice_groups ?? [];
  const sizes = item.options ?? [];
  const [picked, setPicked] = useState(() => defaultPicks(groups));
  const [sizeId, setSizeId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [flagged, setFlagged] = useState<string | null>(null);
  const pushed = useRef(false);

  // The phone's Back closes the sheet. pushState(null) keeps Next's own history state;
  // an entry with custom state makes the router reload the page on Back.
  // Pushed once per sheet: StrictMode's second run (or a new onClose) must not push again.
  useEffect(() => {
    if (!pushed.current) {
      window.history.pushState(null, "");
      pushed.current = true;
    }
    const onPop = () => {
      pushed.current = false;
      onClose();
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [onClose]);

  // Idempotent: the dialog's own close event calls this too.
  const close = () => {
    if (pushed.current) {
      pushed.current = false;
      window.history.back();
    }
    onClose();
  };

  const size = sizes.find((s) => s.id === sizeId);
  const missingSize = sizes.length > 0 && !size;
  const missing = firstMissing(groups, picked);
  const unit = unitPrice(Number(size?.price ?? item.price), groups, picked);
  const total = formatPrice(unit * quantity);
  const action = missingSize
    ? dict.dish.chooseGroup.replace("{group}", dict.dish.size.toLowerCase())
    : missing
      ? dict.dish.chooseGroup.replace("{group}", missing.label)
      : dict.dish.addToOrder.replace("{total}", total);

  const add = () => {
    const target = missingSize ? "size" : missing?.id;
    if (target) {
      setFlagged(target);
      const el = document.getElementById(`group-${target}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.focus();
      return;
    }
    onAdd(
      size && { id: size.id, label: size.label, price: Number(size.price) },
      pickedChoices(groups, picked),
      quantity,
      worstStatus(item.allergen_status, groups, picked),
      matchedAllergens(item.matched_allergens, groups, picked),
    );
    close();
  };

  const need = (g: ChoiceGroup) => {
    const r = requirement(g);
    return dict.dish[r.key].replace("{n}", String(r.n));
  };
  const legend = "flex w-full items-baseline justify-between gap-3 text-base font-semibold text-ink";
  const row = "flex min-h-11 cursor-pointer items-center gap-3 py-1 text-sm text-ink";
  const box = (id: string) =>
    `space-y-1 rounded-xl p-2 outline-none ${flagged === id ? "ring-2 ring-danger-fg" : ""}`;

  return (
    <Sheet
      open
      onClose={close}
      title={item.name}
      footer={
        <div className="flex items-center gap-3">
          <div role="group" aria-label={dict.dish.quantity} className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              aria-label={dict.ui.decrease}
              onClick={() => setQuantity((q) => Math.max(1, q - 1))}
            >
              −
            </Button>
            <span className="w-5 text-center text-sm font-semibold tabular-nums">{quantity}</span>
            <Button
              variant="outline"
              size="icon"
              aria-label={dict.ui.increase}
              onClick={() => setQuantity((q) => Math.min(20, q + 1))}
            >
              +
            </Button>
          </div>
          <Button className="min-h-12 flex-1 text-base" onClick={add}>
            <span aria-live="polite">{action}</span>
          </Button>
        </div>
      }
    >
      {item.image_url && (
        // eslint-disable-next-line @next/next/no-img-element -- venue photos come from any host
        <img src={item.image_url} alt="" className="aspect-[4/3] w-full rounded-xl object-cover" />
      )}
      {item.description && <p className="text-sm text-ink-muted">{item.description}</p>}
      <AllergenChip status={item.allergen_status} matchedAllergens={item.matched_allergens} locale={lang} />

      {sizes.length > 0 && (
        <fieldset id="group-size" tabIndex={-1} className={box("size")}>
          <legend className={legend}>
            <span>{dict.dish.size}</span>
            <span className="text-xs font-normal text-ink-muted">{dict.dish.chooseOne}</span>
          </legend>
          {sizes.map((s) => (
            <label key={s.id} className={row}>
              <input
                type="radio"
                name="size"
                checked={sizeId === s.id}
                onChange={() => {
                  setSizeId(s.id);
                  setFlagged(null);
                }}
                className="h-5 w-5 accent-terracotta"
              />
              <span className="flex-1">{s.label}</span>
              <span className="tabular-nums">{formatPrice(Number(s.price))}</span>
            </label>
          ))}
        </fieldset>
      )}

      {groups.map((g) => {
        const mine = g.choices.filter((c) => picked.includes(c.id)).length;
        const full = !isRadio(g) && g.max_select > 1 && mine >= g.max_select;
        return (
          <fieldset key={g.id} id={`group-${g.id}`} tabIndex={-1} className={box(g.id)}>
            <legend className={legend}>
              <span>{g.label}</span>
              <span className="text-xs font-normal text-ink-muted">{need(g)}</span>
            </legend>
            {(g.kind === "leave_out" || g.choices.some((c) => /^no\s/i.test(c.label))) && (
              <p className="text-xs text-ink-muted">{dict.dish.leaveOutNotice}</p>
            )}
            {g.choices.map((c) => {
              const on = picked.includes(c.id);
              const notFit =
                dietary.includes("vegan") && !c.is_vegan
                  ? dict.dish.notVegan
                  : dietary.includes("vegetarian") && !c.is_vegetarian
                    ? dict.dish.notVegetarian
                    : null;
              return (
                <label key={c.id} className={`${row} ${c.available ? "" : "opacity-50"}`}>
                  <input
                    type={isRadio(g) ? "radio" : "checkbox"}
                    name={g.id}
                    checked={on}
                    disabled={!c.available || (full && !on)}
                    onChange={() => {
                      setPicked((p) => toggle(g, p, c.id));
                      setFlagged(null);
                    }}
                    className="h-5 w-5 accent-terracotta"
                  />
                  <span className="flex-1">
                    {c.label}
                    {!c.available && <span className="ml-2 text-xs italic">{dict.dish.soldOut}</span>}
                  </span>
                  {c.allergen_status !== "no_declared_match" && (
                    <AllergenChip status={c.allergen_status} matchedAllergens={c.matched_allergens} locale={lang} />
                  )}
                  {notFit && <Badge>{notFit}</Badge>}
                  {Number(c.price_delta) > 0 && (
                    <span className="tabular-nums">+{formatPrice(Number(c.price_delta))}</span>
                  )}
                </label>
              );
            })}
          </fieldset>
        );
      })}
    </Sheet>
  );
}
