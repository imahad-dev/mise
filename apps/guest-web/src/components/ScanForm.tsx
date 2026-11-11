"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { getDictionary, withVenue } from "../i18n";
import { useVenue } from "./BrandShell";

const EU14_ALLERGENS = [
  "gluten",
  "milk",
  "eggs",
  "fish",
  "crustaceans",
  "molluscs",
  "tree_nuts",
  "peanuts",
  "soy",
  "celery",
  "mustard",
  "sesame",
  "sulphites",
  "lupin",
] as const;

const DIETS = ["vegetarian", "vegan", "gluten_free"] as const;

export function ScanForm({ token }: { token: string }) {
  const router = useRouter();
  const { slug, name, branded } = useVenue();

  const [language, setLanguage] = useState<"en" | "it">("en");
  const [dietary, setDietary] = useState<string[]>([]);
  const [allergens, setAllergens] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dict = getDictionary(language);

  const toggleDiet = (diet: string) => {
    setDietary((prev) =>
      prev.includes(diet) ? prev.filter((d) => d !== diet) : [...prev, diet]
    );
  };

  const toggleAllergen = (allergen: string) => {
    setAllergens((prev) =>
      prev.includes(allergen)
        ? prev.filter((a) => a !== allergen)
        : [...prev, allergen]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/guest/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          qr_token: token,
          language,
          dietary_preferences: dietary,
          allergens_to_avoid: allergens,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(
          errData?.detail || `Failed to create guest session (${res.status})`
        );
      }

      // Success: cookie set by API, navigate to localized menu
      router.push(`/${language}/menu`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col justify-center px-4 py-8 sm:px-6 lg:px-8">
      <div className="max-w-md w-full mx-auto space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          {branded && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`/venues/${slug}/mark.svg`} alt="" width={64} height={64} className="mx-auto rounded-2xl" />
          )}
          <h1 className="text-3xl text-ink">
            {withVenue(dict.ui.welcomeTitle, name)}
          </h1>
          <p className="text-sm text-ink-muted">{dict.ui.welcomeSubtitle}</p>
        </div>

        {/* One line here; the full allergen notice stays in the order sheet before confirming. */}
        <p className="text-center text-xs text-warn-fg">{dict.ui.noticeShort}</p>

        {error && (
          <div className="rounded-xl p-3 bg-danger-bg border border-danger-fg/40 text-xs text-danger-fg">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Language selector */}
          <div className="bg-card p-4 rounded-2xl border border-line space-y-2.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-muted">
              {dict.ui.selectLanguage}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setLanguage("en")}
                className={`py-2 px-3 rounded-xl text-sm font-medium transition-all ${
                  language === "en"
                    ? "bg-terracotta text-cream shadow-md shadow-ink/10"
                    : "bg-paper-2 text-ink-muted hover:bg-line"
                }`}
              >
                🇬🇧 English
              </button>
              <button
                type="button"
                onClick={() => setLanguage("it")}
                className={`py-2 px-3 rounded-xl text-sm font-medium transition-all ${
                  language === "it"
                    ? "bg-terracotta text-cream shadow-md shadow-ink/10"
                    : "bg-paper-2 text-ink-muted hover:bg-line"
                }`}
              >
                🇮🇹 Italiano
              </button>
            </div>
          </div>

          {/* Diet and allergen choices fold away, so most guests reach the menu in one tap. */}
          <details className="group rounded-2xl border border-line bg-card">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold text-ink">
              <span>{dict.ui.allergyToggle}</span>
              <span className="text-xs font-medium text-ink-muted">
                {dietary.length + allergens.length > 0 ? `${dietary.length + allergens.length} ✓` : "+"}
              </span>
            </summary>
            <div className="space-y-4 px-4 pb-4">
          {/* Diets selector */}
          <div className="space-y-2.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-muted">
              {dict.ui.selectDietary}
            </label>
            <div className="flex flex-wrap gap-2">
              {DIETS.map((diet) => {
                const selected = dietary.includes(diet);
                return (
                  <button
                    key={diet}
                    type="button"
                    onClick={() => toggleDiet(diet)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                      selected
                        ? "bg-safe-bg text-safe-fg border-safe-fg/40"
                        : "bg-paper-2 text-ink-muted border-line hover:border-ink-muted"
                    }`}
                  >
                    {dict.dietary[diet] || diet} {selected ? "✓" : "+"}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Allergens selector */}
          <div className="space-y-2.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-muted">
              {dict.ui.selectAllergens}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {EU14_ALLERGENS.map((allergen) => {
                const selected = allergens.includes(allergen);
                return (
                  <button
                    key={allergen}
                    type="button"
                    onClick={() => toggleAllergen(allergen)}
                    className={`px-2.5 py-1.5 rounded-xl text-xs font-medium border text-left flex items-center justify-between transition-all ${
                      selected
                        ? "bg-danger-bg text-danger-fg border-danger-fg/40"
                        : "bg-paper-2 text-ink-muted border-line hover:border-ink-muted"
                    }`}
                  >
                    <span className="truncate">{dict.allergens[allergen] || allergen}</span>
                    <span className="text-[10px] ml-1 opacity-70">
                      {selected ? "✕" : "+"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
            </div>
          </details>

          {/* Submit button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 px-4 rounded-2xl bg-terracotta hover:bg-terracotta-strong active:scale-[0.98] text-cream font-semibold text-sm shadow-xl shadow-ink/10 transition-all disabled:opacity-50"
          >
            {loading ? "..." : dict.ui.continueToMenu}
          </button>
        </form>
      </div>
    </div>
  );
}
