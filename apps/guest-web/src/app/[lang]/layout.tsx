import React from "react";
import type { Metadata, Viewport } from "next";
import { notFound, redirect } from "next/navigation";
import { BrandShell } from "../../components/BrandShell";
import { ScanAgain } from "../../components/ScanAgain";
import { isGuestLanguage, isRtl, languageFor } from "../../i18n/languages";
import { naskh } from "../../lib/naskh";
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
  if (!isGuestLanguage(lang)) notFound();
  const v = await venueFromSession();
  if (!v) return <ScanAgain lang={lang} />;
  const want = languageFor(v);
  if (want !== lang) redirect(`/${want}/menu`);
  const rtl = isRtl(lang);
  return (
    // display: contents keeps the page layout; lang and dir are inherited, and sheets (<dialog>) sit inside.
    <div lang={lang} dir={rtl ? "rtl" : "ltr"} className={`contents ${rtl ? naskh.variable : ""}`}>
      <BrandShell
        key={v.slug}
        venue={{ slug: v.slug, name: v.name, languages: v.languages, defaultLanguage: v.defaultLanguage }}
        welcomeFor={v.visitId}
      >
        {children}
      </BrandShell>
    </div>
  );
}
