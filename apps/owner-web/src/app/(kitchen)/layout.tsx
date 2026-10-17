import React from "react";

export default function KitchenLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-black text-zinc-100 flex flex-col font-sans select-none antialiased">
      {children}
    </div>
  );
}
