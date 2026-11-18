import type { Metadata } from "next";

// The presenter page lists the demo venues and is Mise-branded. No guest flow links here.
export const metadata: Metadata = {
  title: "Mise: Restaurant Revenue Copilot",
  description: "Restaurant revenue copilot and real-time operations platform",
  manifest: "/manifest.json",
  icons: { icon: "/brand/logo-mark.svg", apple: "/brand/logo-mark.svg" },
};

export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
