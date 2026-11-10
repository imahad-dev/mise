import React from "react";
import type { Metadata, Viewport } from "next";
import { BrandShell } from "../../components/BrandShell";
import { ScanAgain } from "../../components/ScanAgain";
import { venueFromSession } from "../../lib/venue-server";
import { venueMetadata, venueViewport } from "../../lib/venue-meta";

export async function generateMetadata(): Promise<Metadata> {
  const v = await venueFromSession();
  return v ? venueMetadata(v) : { title: "Menu" };
}

export async function generateViewport(): Promise<Viewport> {
  return venueViewport(await venueFromSession());
}

export default async function GuestLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  const v = await venueFromSession();
  if (!v) return <ScanAgain lang={lang} />;
  return (
    <BrandShell key={v.slug} venue={{ slug: v.slug, name: v.name }} welcomeFor={v.visitId}>
      {children}
    </BrandShell>
  );
}
