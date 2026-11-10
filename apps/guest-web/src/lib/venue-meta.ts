import type { Metadata, Viewport } from "next";
import { venueBrand } from "ui";

export function venueMetadata(v: { slug: string; name: string }): Metadata {
  const icon = `/venues/${v.slug}/mark.svg`;
  return {
    title: v.name,
    ...(venueBrand(v.slug) && {
      manifest: `/venues/${v.slug}/manifest.webmanifest`,
      icons: { icon, apple: icon },
    }),
    appleWebApp: { capable: true, title: v.name },
  };
}

export function venueViewport(v: { slug: string; name: string } | null): Viewport {
  return { themeColor: venueBrand(v?.slug)?.tokens.deep ?? "#ffffff" };
}
