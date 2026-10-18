"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [demoMode, setDemoMode] = useState(false);
  const [role, setRole] = useState<"owner" | "staff">("owner");
  const [secret, setSecret] = useState("");
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState<"owner" | "staff" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadConfig() {
      try {
        const res = await fetch("/api/auth/config");
        if (res.ok) {
          const data = await res.json();
          setDemoMode(Boolean(data.demo_mode));
        }
      } catch {
        // Default to non-demo if config request fails
      }
    }
    loadConfig();
  }, []);

  const handleDemoLogin = async (selectedRole: "owner" | "staff") => {
    setDemoLoading(selectedRole);
    setError(null);
    try {
      const res = await fetch("/api/auth/demo-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: selectedRole }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Rate limit exceeded: maximum 20 demo logins per minute.");
        }
        throw new Error(`Demo login failed (${res.status})`);
      }
      if (selectedRole === "staff") {
        router.push("/kitchen");
      } else {
        router.push("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDemoLoading(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, secret }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error("Invalid credentials");
        }
        if (res.status === 429) {
          throw new Error("Too many failed attempts. Please wait 5 minutes.");
        }
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `Login failed (${res.status})`);
      }

      if (role === "staff") {
        router.push("/kitchen");
      } else {
        router.push("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070B10] text-[#F3F8FC] flex flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
      {/* Demo Environment Banner */}
      {demoMode && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-[#FF9F2E]/10 border-b border-[#FF9F2E]/30 text-[#FF9F2E] px-4 py-2 text-center text-xs font-semibold backdrop-blur-md">
          ⚠️ Demo environment: synthetic data
        </div>
      )}

      <div className="max-w-md w-full mx-auto space-y-8">
        <div className="text-center space-y-3">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl glass-panel p-2.5">
            <Image
              src="/brand/logo-mark.svg"
              alt="Mise Logo"
              width={40}
              height={40}
              className="w-10 h-10"
              priority
            />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight">
            Sign In to <span className="gradient-text">Mise</span>
          </h1>
          <p className="text-xs text-[#8FA3B3]">
            Restaurant Revenue Copilot & Kitchen Operations
          </p>
        </div>

        {error && (
          <div className="p-3.5 rounded-xl bg-[#EF4444]/15 border border-[#EF4444]/40 text-xs text-[#EF4444] font-medium text-center">
            {error}
          </div>
        )}

        {/* Demo Mode Quick Access */}
        {demoMode && (
          <div className="glass-panel p-6 space-y-4">
            <div className="text-center space-y-1">
              <h2 className="text-sm font-bold text-[#F3F8FC]">
                Judge & Evaluator Quick Access
              </h2>
              <p className="text-xs text-[#8FA3B3]">
                Instant demo sign-in with preloaded restaurant operations
              </p>
            </div>

            <div className="space-y-3 pt-1">
              <button
                type="button"
                onClick={() => handleDemoLogin("owner")}
                disabled={demoLoading !== null}
                className="btn-primary w-full shadow-lg shadow-cyan-950/40"
              >
                {demoLoading === "owner" ? "Signing In..." : "Enter as demo owner"}
              </button>

              <button
                type="button"
                onClick={() => handleDemoLogin("staff")}
                disabled={demoLoading !== null}
                className="btn-ghost w-full"
              >
                {demoLoading === "staff" ? "Opening..." : "Open kitchen display (demo staff)"}
              </button>
            </div>
          </div>
        )}

        {/* Standard / Admin Sign-in */}
        <div className="mise-card p-6 sm:p-8 space-y-6">
          <div className="border-b border-[#38BDF8]/15 pb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[#8FA3B3]">
              {demoMode ? "Admin sign-in" : "Sign In with Credentials"}
            </h3>
          </div>

          {/* Role Toggle */}
          <div className="grid grid-cols-2 gap-2 p-1 bg-[#070B10] rounded-xl border border-[#38BDF8]/15">
            <button
              type="button"
              onClick={() => {
                setRole("owner");
                setSecret("");
                setError(null);
              }}
              className={`min-h-[44px] py-2 px-3 rounded-lg text-xs font-semibold transition-all ${
                role === "owner"
                  ? "bg-[#0D141B] text-[#22D3EE] border border-[#38BDF8]/30 shadow-sm"
                  : "text-[#8FA3B3] hover:text-[#F3F8FC]"
              }`}
            >
              👑 Owner
            </button>
            <button
              type="button"
              onClick={() => {
                setRole("staff");
                setSecret("");
                setError(null);
              }}
              className={`min-h-[44px] py-2 px-3 rounded-lg text-xs font-semibold transition-all ${
                role === "staff"
                  ? "bg-[#0D141B] text-[#22D3EE] border border-[#38BDF8]/30 shadow-sm"
                  : "text-[#8FA3B3] hover:text-[#F3F8FC]"
              }`}
            >
              👨‍🍳 Staff / Kitchen
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-[#8FA3B3] mb-1.5">
                {role === "owner" ? "Owner API Key" : "Staff PIN (4 digits)"}
              </label>
              <input
                type="password"
                maxLength={role === "staff" ? 8 : 128}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={role === "owner" ? "Enter owner key..." : "e.g. 0000"}
                required
                className="w-full min-h-[44px] px-3.5 py-2.5 rounded-xl bg-[#070B10] border border-[#38BDF8]/20 text-sm text-[#F3F8FC] placeholder:text-[#8FA3B3]/50 focus:outline-none focus:border-[#22D3EE] focus:ring-1 focus:ring-[#22D3EE]"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !secret.trim()}
              className="btn-ghost w-full disabled:opacity-40"
            >
              {loading
                ? "Authenticating..."
                : `Sign In as ${role === "owner" ? "Owner" : "Kitchen Staff"}`}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
