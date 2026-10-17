import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mise — Operations & Kitchen",
  description: "Restaurant management dashboard and kitchen display system",
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
