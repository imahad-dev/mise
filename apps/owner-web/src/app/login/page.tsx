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
    <div className="min-h-screen bg-paper text-ink flex flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
      {/* Demo Environment Banner */}
      {demoMode && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-warn-bg border-b border-warn-fg/30 text-warn-fg px-4 py-2 text-center text-xs font-semibold backdrop-blur-md">
          ⚠️ Demo environment: synthetic data
        </div>
      )}

      <div className="max-w-md w-full mx-auto space-y-8">
        <div className="text-center space-y-3">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mise-card p-2.5">
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
            Sign In to <span className="text-terracotta">Mise</span>
          </h1>
          <p className="text-xs text-ink-muted">
            Restaurant Revenue Copilot & Kitchen Operations
          </p>
        </div>

        {error && (
          <div className="p-3.5 rounded-xl bg-danger-bg border border-danger-fg text-xs text-danger-fg font-medium text-center">
            {error}
          </div>
        )}

        {/* Demo Mode Quick Access */}
        {demoMode && (
          <div className="mise-card p-6 space-y-4">
            <div className="text-center space-y-1">
              <h2 className="text-sm font-bold text-ink">
                Try the demo
              </h2>
              <p className="text-xs text-ink-muted">
                Instant demo sign-in with preloaded restaurant operations
              </p>
            </div>

            <div className="space-y-3 pt-1">
              <button
                type="button"
                onClick={() => handleDemoLogin("owner")}
                disabled={demoLoading !== null}
                className="btn-primary w-full shadow-lg shadow-ink/10"
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
          <div className="border-b border-line pb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              {demoMode ? "Admin sign-in" : "Sign In with Credentials"}
            </h3>
          </div>

          {/* Role Toggle */}
          <div className="grid grid-cols-2 gap-2 p-1 bg-paper rounded-xl border border-line">
            <button
              type="button"
              onClick={() => {
                setRole("owner");
                setSecret("");
                setError(null);
              }}
              className={`min-h-[44px] py-2 px-3 rounded-lg text-xs font-semibold transition-all ${
                role === "owner"
                  ? "bg-card text-terracotta border border-line shadow-sm"
                  : "text-ink-muted hover:text-ink"
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
                  ? "bg-card text-terracotta border border-line shadow-sm"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              👨‍🍳 Staff / Kitchen
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-ink-muted mb-1.5">
                {role === "owner" ? "Owner API Key" : "Staff PIN (4 digits)"}
              </label>
              <input
                type="password"
                maxLength={role === "staff" ? 8 : 128}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={role === "owner" ? "Enter owner key..." : "e.g. 0000"}
                required
                className="w-full min-h-[44px] px-3.5 py-2.5 rounded-xl bg-paper border border-line text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:border-terracotta focus:ring-1 focus:ring-terracotta"
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
