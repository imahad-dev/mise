"use client";

import React, { useState } from "react";
import { getDictionary } from "../i18n";

export interface ChatPanelProps {
  locale?: string;
}

interface ChatMessage {
  sender: "user" | "assistant";
  text: string;
}

export function ChatPanel({ locale = "en" }: ChatPanelProps) {
  const dict = getDictionary(locale);
  const [isOpen, setIsOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  if (hidden) {
    return null;
  }

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isLoading) return;

    setMessages((prev) => [...prev, { sender: "user", text: query }]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch("/api/guest/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query }),
      });

      if (res.status === 404 || res.status === 503) {
        // Requirement: "it must hide itself if the endpoint returns 404 or 503"
        setHidden(true);
        return;
      }

      if (res.ok) {
        const data = await res.json();
        const reply = data.reply || data.response || data.message || "Thank you for asking.";
        setMessages((prev) => [...prev, { sender: "assistant", text: reply }]);
      } else {
        setMessages((prev) => [
          ...prev,
          { sender: "assistant", text: "Assistant currently unavailable." },
        ]);
      }
    } catch {
      // Network or unexpected failure
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", text: "Unable to connect to assistant." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-40">
      {!isOpen ? (
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-lg shadow-emerald-950/50 transition-all text-sm active:scale-95"
          aria-label={dict.ui.chatTitle}
        >
          <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
            <path d="M2 5a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6.414l-2.707 2.707A1 1 0 012 17V5z" />
          </svg>
          {dict.ui.chatTitle}
        </button>
      ) : (
        <div className="w-80 sm:w-96 rounded-2xl bg-zinc-900 border border-zinc-800 shadow-2xl flex flex-col max-h-[500px] overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 bg-zinc-800/80 border-b border-zinc-700/60 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <h3 className="text-sm font-semibold text-zinc-100">{dict.ui.chatTitle}</h3>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-zinc-400 hover:text-zinc-200 text-xs px-2 py-1 rounded"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          {/* Privacy Notice Banner */}
          <div className="px-3 py-2 bg-amber-950/40 border-b border-amber-900/30 text-[11px] text-amber-300/90 leading-tight">
            ⚠️ {dict.ui.chatNotice}
          </div>

          {/* Messages */}
          <div className="p-3 flex-1 overflow-y-auto space-y-2 min-h-[160px] max-h-[300px] text-xs">
            {messages.length === 0 ? (
              <p className="text-zinc-500 text-center py-6 italic">
                Ask about dish ingredients or dietary options.
              </p>
            ) : (
              messages.map((m, idx) => (
                <div
                  key={idx}
                  className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-xl px-3 py-2 ${
                      m.sender === "user"
                        ? "bg-emerald-600 text-white rounded-br-none"
                        : "bg-zinc-800 text-zinc-200 rounded-bl-none border border-zinc-700"
                    }`}
                  >
                    {m.text}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-zinc-800 text-zinc-400 rounded-xl px-3 py-2 text-xs">
                  Thinking...
                </div>
              </div>
            )}
          </div>

          {/* Input form */}
          <form onSubmit={handleSend} className="p-2 border-t border-zinc-800 flex gap-1.5 bg-zinc-900">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={dict.ui.chatPlaceholder}
              className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-emerald-500 placeholder:text-zinc-500"
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-medium"
            >
              {dict.ui.chatSend}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
