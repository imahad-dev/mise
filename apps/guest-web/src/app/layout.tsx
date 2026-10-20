import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#070B10",
};

export const metadata: Metadata = {
  title: "Mise: Restaurant Revenue Copilot",
  description: "Restaurant revenue copilot and real-time operations platform",
  manifest: "/manifest.json",
  icons: {
    icon: "/brand/logo-mark.svg",
    apple: "/brand/logo-mark.svg",
  },
  openGraph: {
    title: "Mise: Restaurant Revenue Copilot",
    description: "Restaurant revenue copilot and real-time operations platform",
  },
  twitter: {
    card: "summary",
    title: "Mise: Restaurant Revenue Copilot",
    description: "Restaurant revenue copilot and real-time operations platform",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Mise",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased dark bg-[#070B10] text-[#F3F8FC]">
      <body className="min-h-full flex flex-col font-sans bg-[#070B10] text-[#F3F8FC]">
        {children}
      </body>
    </html>
  );
}
