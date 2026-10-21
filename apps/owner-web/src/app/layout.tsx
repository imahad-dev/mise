import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mise — Operations & Kitchen",
  description: "Restaurant management dashboard and kitchen display system",
  icons: {
    icon: "/brand/logo-mark.svg",
    apple: "/brand/logo-mark.svg",
  },
  openGraph: {
    title: "Mise Operations & Kitchen",
    description: "Restaurant management dashboard and kitchen display system",
  },
  twitter: {
    card: "summary",
    title: "Mise Operations & Kitchen",
    description: "Restaurant management dashboard and kitchen display system",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
