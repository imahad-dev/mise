/** A dish's main ingredients as short tags: the menu's own order, no blanks or repeats, capitalised. */
export function mainIngredients(ingredients: readonly string[] | undefined, max = 4): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of ingredients ?? []) {
    const name = raw.trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key)) continue;
    seen.add(key);
    out.push(name[0].toUpperCase() + name.slice(1));
    if (out.length === max) break;
  }
  return out;
}
