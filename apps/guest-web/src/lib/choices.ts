export type AllergenStatus = "contains" | "unverified" | "no_declared_match";

export interface Choice {
  id: string;
  label: string;
  price_delta: string;
  allergens: string[];
  is_vegetarian: boolean;
  is_vegan: boolean;
  available: boolean;
  is_default: boolean;
  allergen_status: AllergenStatus;
  matched_allergens: string[];
}

export interface ChoiceGroup {
  id: string;
  label: string;
  kind: "pick" | "add" | "leave_out";
  min_select: number;
  max_select: number;
  choices: Choice[];
}

export interface CartChoice {
  id: string;
  group: string;
  kind: ChoiceGroup["kind"];
  label: string;
  priceDelta: number;
}

const inGroup = (g: ChoiceGroup, picked: string[]) => picked.filter((id) => g.choices.some((c) => c.id === id));

export const isRadio = (g: ChoiceGroup) => g.min_select === 1 && g.max_select === 1;

export function defaultPicks(groups: ChoiceGroup[]): string[] {
  return groups.flatMap((g) => g.choices.filter((c) => c.is_default && c.available).map((c) => c.id));
}

export function firstMissing(groups: ChoiceGroup[], picked: string[]): ChoiceGroup | null {
  return groups.find((g) => inGroup(g, picked).length < g.min_select) ?? null;
}

/**
 * The picks after tapping `id`. A radio button swaps (tapping it again keeps it); a full group
 * ignores another tick; a sold-out choice or one from another group changes nothing.
 */
export function toggle(group: ChoiceGroup, picked: string[], id: string): string[] {
  if (!group.choices.some((c) => c.id === id && c.available)) return picked;
  const mine = inGroup(group, picked);
  const others = picked.filter((p) => !mine.includes(p));
  if (isRadio(group)) return [...others, id];
  if (mine.includes(id)) return picked.filter((p) => p !== id);
  if (group.max_select === 1) return [...others, id];
  return mine.length >= group.max_select ? picked : [...picked, id];
}

export function pickedChoices(groups: ChoiceGroup[], picked: string[]): CartChoice[] {
  return groups.flatMap((g) =>
    g.choices
      .filter((c) => picked.includes(c.id))
      .map((c) => ({ id: c.id, group: g.label, kind: g.kind, label: c.label, priceDelta: Number(c.price_delta) })),
  );
}

export function unitPrice(base: number, groups: ChoiceGroup[], picked: string[]): number {
  return pickedChoices(groups, picked).reduce((sum, c) => sum + c.priceDelta, base);
}

const RANK: AllergenStatus[] = ["no_declared_match", "unverified", "contains"];

/** For display only: the server decides. */
export function worstStatus(dish: AllergenStatus, groups: ChoiceGroup[], picked: string[]): AllergenStatus {
  const statuses = groups.flatMap((g) => g.choices.filter((c) => picked.includes(c.id)).map((c) => c.allergen_status));
  return [dish, ...statuses].reduce((a, b) => (RANK.indexOf(b) > RANK.indexOf(a) ? b : a));
}

/** The dish's own matches plus those of the picked choices, once each. For display only. */
export function matchedAllergens(dish: string[] | undefined, groups: ChoiceGroup[], picked: string[]): string[] {
  const picks = groups.flatMap((g) => g.choices.filter((c) => picked.includes(c.id)));
  return [...new Set([...(dish ?? []), ...picks.flatMap((c) => c.matched_allergens)])];
}

/**
 * Whether + must open the dish page: a size to choose, a required group the defaults leave empty,
 * or a default that costs money or carries an allergen warning (one tap never hides either).
 */
export function needsPage(item: { options?: unknown[]; choice_groups?: ChoiceGroup[] }): boolean {
  const groups = item.choice_groups ?? [];
  const picks = defaultPicks(groups);
  const loud = groups.some((g) =>
    g.choices.some(
      (c) => picks.includes(c.id) && (Number(c.price_delta) > 0 || c.allergen_status !== "no_declared_match"),
    ),
  );
  return (item.options?.length ?? 0) > 0 || loud || firstMissing(groups, picks) !== null;
}

export function requirement(g: ChoiceGroup): { key: "chooseOne" | "choose" | "upTo" | "optional"; n: number } {
  if (g.min_select === 1 && g.max_select === 1) return { key: "chooseOne", n: 1 };
  if (g.min_select > 0) return { key: "choose", n: g.min_select };
  return g.max_select > 1 ? { key: "upTo", n: g.max_select } : { key: "optional", n: 1 };
}
