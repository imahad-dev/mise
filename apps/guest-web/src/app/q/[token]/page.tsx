import React from "react";
import type { Metadata, Viewport } from "next";
import { BrandShell } from "../../../components/BrandShell";
import { ScanAgain } from "../../../components/ScanAgain";
import { ScanForm } from "../../../components/ScanForm";
import { venueFromQr } from "../../../lib/venue-server";
import { venueMetadata, venueViewport } from "../../../lib/venue-meta";

type Props = { params: Promise<{ token: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const v = await venueFromQr((await params).token);
  return v ? venueMetadata(v) : { title: "Menu" };
}

export async function generateViewport({ params }: Props): Promise<Viewport> {
  return venueViewport(await venueFromQr((await params).token));
}

export default async function ScanPage({ params }: Props) {
  const { token } = await params;
  const v = await venueFromQr(token);
  if (!v) return <ScanAgain lang="en" />;
  return (
    <BrandShell key={v.slug} venue={v}>
      <ScanForm token={token} />
    </BrandShell>
  );
}
