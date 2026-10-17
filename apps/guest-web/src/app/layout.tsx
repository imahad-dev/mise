import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#18181b",
};

export const metadata: Metadata = {
  title: "Mise — Guest",
  description: "Order from your table in your language",
  manifest: "/manifest.json",
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
    <html lang="en" className="h-full antialiased dark bg-zinc-950 text-zinc-100">
      <body className="min-h-full flex flex-col font-sans bg-zinc-950 text-zinc-100">
        {children}
      </body>
    </html>
  );
}
