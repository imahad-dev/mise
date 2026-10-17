"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState<"owner" | "staff">("owner");
  const [secret, setSecret] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

      // Role redirect
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
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="max-w-md w-full mx-auto space-y-8">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-600/20 text-emerald-400 font-bold text-2xl border border-emerald-500/30">
            M
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
            Sign In to Mise
          </h1>
          <p className="text-xs text-zinc-400">
            Restaurant Operations & Kitchen Display
          </p>
        </div>

        {error && (
          <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800 text-xs text-rose-300 font-medium text-center">
            {error}
          </div>
        )}

        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6">
          {/* Role Toggle */}
          <div className="grid grid-cols-2 gap-2 p-1 bg-zinc-950 rounded-2xl border border-zinc-800">
            <button
              type="button"
              onClick={() => {
                setRole("owner");
                setSecret("");
                setError(null);
              }}
              className={`py-2 px-3 rounded-xl text-xs font-semibold transition-all ${
                role === "owner"
                  ? "bg-zinc-800 text-emerald-400 shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
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
              className={`py-2 px-3 rounded-xl text-xs font-semibold transition-all ${
                role === "staff"
                  ? "bg-zinc-800 text-emerald-400 shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              👨‍🍳 Staff / Kitchen
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                {role === "owner" ? "Owner API Key / Password" : "Staff PIN (4 digits)"}
              </label>
              <input
                type={role === "owner" ? "password" : "password"}
                maxLength={role === "staff" ? 8 : 128}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={role === "owner" ? "Enter owner key..." : "e.g. 0000"}
                autoFocus
                required
                className="w-full px-3.5 py-2.5 rounded-xl bg-zinc-950 border border-zinc-700/80 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !secret.trim()}
              className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-40 text-white font-semibold text-xs shadow-lg shadow-emerald-950/60 transition-all"
            >
              {loading ? "Authenticating..." : `Sign In as ${role === "owner" ? "Owner" : "Kitchen Staff"}`}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
