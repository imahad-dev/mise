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
    <div className="min-h-screen bg-espresso text-cream flex flex-col font-sans select-none antialiased">
      {demoMode && (
        <div className="bg-kds-warn/15 border-b border-kds-warn text-kds-warn px-4 py-1.5 text-center text-xs font-semibold backdrop-blur-md sticky top-0 z-50">
          ⚠️ Demo environment: synthetic data
        </div>
      )}
      {children}
    </div>
  );
}
