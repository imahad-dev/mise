"use client";

import type { ReactNode } from "react";

interface Favourite {
  id: string;
  name: string;
  featured?: boolean;
  available?: boolean;
  image_url?: string | null;
}

/** Featured dishes with a photo, in menu order; tapping one opens its dish sheet. */
export function FavouritesStrip<T extends Favourite>({
  items,
  title,
  price,
  onOpen,
}: {
  items: T[];
  title: string;
  price: (item: T) => ReactNode;
  onOpen: (item: T) => void;
}) {
  const shown = items.filter((i) => i.featured && i.image_url && i.available !== false);
  if (shown.length === 0) return null;
  return (
    <section aria-labelledby="favourites-title">
      <h2 id="favourites-title" className="border-b border-line pb-1 text-lg font-semibold italic text-terracotta">
        {title}
      </h2>
      <ul className="-mx-4 mt-3 flex snap-x gap-3 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6">
        {shown.map((item) => (
          <li key={item.id} className="w-40 shrink-0 snap-start">
            <button type="button" className="block w-full text-start" onClick={() => onOpen(item)}>
              {/* eslint-disable-next-line @next/next/no-img-element -- small local WebP, lazy */}
              <img
                src={item.image_url!}
                loading="lazy"
                alt=""
                width={800}
                height={600}
                className="aspect-[4/3] w-full rounded-xl object-cover"
              />
              <span className="mt-1.5 block text-sm font-semibold text-ink">{item.name}</span>
              <span className="block text-sm text-ink">{price(item)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
