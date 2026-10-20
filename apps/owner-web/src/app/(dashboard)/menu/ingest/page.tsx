"use client";

import React, { useState } from "react";

interface IngestedTranslation {
  language: string;
  name: string;
  description: string;
}

interface IngestedItem {
  id: string;
  category: string;
  price: number;
  unit_cost: number | null;
  allergens: string[];
  allergen_verified: boolean;
  translations: IngestedTranslation[];
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

export default function MenuIngestPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [imageUrl, setImageUrl] = useState("https://example.com/trattoria-menu.jpg");
  const [language, setLanguage] = useState("it");
  const [loading, setLoading] = useState(false);
  const [createdCount, setCreatedCount] = useState<number | null>(null);
  const [items, setItems] = useState<IngestedItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setCreatedCount(null);
    setItems([]);

    try {
      const res = await fetch(`/api/restaurants/${slug}/menu-items/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_url: imageUrl, language }),
      });

      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Demo abuse limit reached: Maximum 3 menu photo ingestions per hour per IP.");
        }
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `Menu ingest failed (${res.status})`);
      }

      const data = await res.json();
      setCreatedCount(data.created_count);
      setItems(data.items || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          Visual Menu <span className="gradient-text">Ingestion (VLM)</span>
        </h1>
        <p className="text-xs text-[#8FA3B3] mt-1">
          Extract printed restaurant menus, dish names, prices, and allergen disclosures automatically using AI assistant VLM
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-[#EF4444]/15 border border-[#EF4444]/40 text-xs text-[#EF4444]">
          {error}
        </div>
      )}

      {/* Ingest Form Card */}
      <div className="mise-card p-6 sm:p-8 space-y-6">
        <form onSubmit={handleIngest} className="space-y-5">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="md:col-span-2 space-y-1.5">
              <label className="block text-xs font-semibold text-[#8FA3B3]">
                Menu Image URL (JPEG, PNG, or WebP)
              </label>
              <input
                type="url"
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                required
                placeholder="https://example.com/menu.jpg"
                className="w-full min-h-[44px] px-3.5 py-2.5 rounded-xl bg-[#070B10] border border-[#38BDF8]/20 text-sm text-[#F3F8FC] placeholder:text-[#8FA3B3]/40 focus:outline-none focus:border-[#22D3EE] focus:ring-1 focus:ring-[#22D3EE]"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-[#8FA3B3]">
                Primary Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full min-h-[44px] px-3.5 py-2.5 rounded-xl bg-[#070B10] border border-[#38BDF8]/20 text-sm text-[#F3F8FC] focus:outline-none focus:border-[#22D3EE]"
              >
                <option value="it">Italian (Italiano)</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
            <span className="text-xs text-[#8FA3B3]">
              ℹ️ Demo limit: 3 image ingestions per hour per client IP
            </span>
            <button
              type="submit"
              disabled={loading || !imageUrl.trim()}
              className="btn-primary min-w-[200px] shadow-lg shadow-cyan-950/40"
            >
              {loading ? "Ingesting via VLM..." : "Analyze & Ingest Menu"}
            </button>
          </div>
        </form>
      </div>

      {/* Success banner & results */}
      {createdCount !== null && (
        <div className="glass-panel p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-[#38BDF8]/15 pb-4">
            <div>
              <span className="text-xs text-[#34D399] font-bold uppercase tracking-wider">
                ✓ Processing Completed
              </span>
              <h2 className="text-xl font-bold text-[#F3F8FC]">
                {createdCount} Menu Items Created
              </h2>
            </div>
            <span className="chip chip-safe">
              VLM Extraction Successful
            </span>
          </div>

          {items.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {items.map((item) => (
                <div key={item.id} className="mise-card p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase text-[#22D3EE]">
                      {item.category}
                    </span>
                    <span className="text-sm font-extrabold text-[#F3F8FC]">
                      €{item.price.toFixed(2)}
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-[#F3F8FC]">
                    {item.translations[0]?.name || "Item"}
                  </h3>
                  <p className="text-xs text-[#8FA3B3] line-clamp-2">
                    {item.translations[0]?.description || "Extracted from menu image."}
                  </p>
                  {item.allergens && item.allergens.length > 0 && (
                    <div className="pt-2 flex flex-wrap gap-1">
                      {item.allergens.map((alg) => (
                        <span key={alg} className="chip chip-unverified text-[10px]">
                          {alg}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
