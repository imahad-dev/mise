"use client";

import React, { useEffect, useState } from "react";

export default function KitchenLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    async function loadConfig() {
      try {
        const res = await fetch("/api/auth/config");
        if (res.ok) {
          const data = await res.json();
          setDemoMode(Boolean(data.demo_mode));
        }
      } catch {
        // Ignore network errors in config
      }
    }
    loadConfig();
  }, []);

  return (
    <div className="min-h-screen bg-[#070B10] text-[#F3F8FC] flex flex-col font-sans select-none antialiased">
      {demoMode && (
        <div className="bg-[#FF9F2E]/10 border-b border-[#FF9F2E]/30 text-[#FF9F2E] px-4 py-1.5 text-center text-xs font-semibold backdrop-blur-md sticky top-0 z-50">
          ⚠️ Demo environment: synthetic data
        </div>
      )}
      {children}
    </div>
  );
}
