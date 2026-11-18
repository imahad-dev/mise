import { venueBrand } from "ui";

export async function GET(_req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const brand = venueBrand(slug);
  if (!brand) return new Response("Not found", { status: 404 });
  return Response.json(
    {
      name: brand.name,
      short_name: brand.name,
      start_url: "/en/menu",
      display: "standalone",
      background_color: brand.tokens.surface,
      theme_color: brand.tokens.deep,
      icons: [{ src: `/venues/${slug}/mark.svg`, sizes: "any", type: "image/svg+xml" }],
    },
    { headers: { "content-type": "application/manifest+json" } },
  );
}
