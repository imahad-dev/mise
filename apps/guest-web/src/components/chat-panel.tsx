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
          className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-terracotta hover:bg-terracotta text-cream font-medium shadow-lg shadow-ink/10 transition-all text-sm active:scale-95"
          aria-label={dict.ui.chatTitle}
        >
          <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
            <path d="M2 5a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6.414l-2.707 2.707A1 1 0 012 17V5z" />
          </svg>
          {dict.ui.chatTitle}
        </button>
      ) : (
        <div className="w-80 sm:w-96 rounded-2xl bg-card border border-line shadow-2xl flex flex-col max-h-[500px] overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 bg-paper-2 border-b border-line flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-olive" />
              <h3 className="text-sm font-semibold text-ink">{dict.ui.chatTitle}</h3>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-ink-muted hover:text-ink text-xs px-2 py-1 rounded"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          {/* Privacy Notice Banner */}
          <div className="px-3 py-2 bg-warn-bg border-b border-warn-fg/30 text-[11px] text-warn-fg/90 leading-tight">
            ⚠️ {dict.ui.chatNotice}
          </div>

          {/* Messages */}
          <div className="p-3 flex-1 overflow-y-auto space-y-2 min-h-[160px] max-h-[300px] text-xs">
            {messages.length === 0 ? (
              <p className="text-ink-muted text-center py-6 italic">
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
                        ? "bg-terracotta text-cream rounded-br-none"
                        : "bg-paper-2 text-ink rounded-bl-none border border-line"
                    }`}
                  >
                    {m.text}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-paper-2 text-ink-muted rounded-xl px-3 py-2 text-xs">
                  Thinking...
                </div>
              </div>
            )}
          </div>

          {/* Input form */}
          <form onSubmit={handleSend} className="p-2 border-t border-line flex gap-1.5 bg-card">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={dict.ui.chatPlaceholder}
              className="flex-1 bg-paper border border-line rounded-lg px-2.5 py-1.5 text-xs text-ink focus:outline-none focus:border-terracotta placeholder:text-ink-muted"
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="px-3 py-1.5 rounded-lg bg-terracotta hover:bg-terracotta disabled:opacity-50 text-cream text-xs font-medium"
            >
              {dict.ui.chatSend}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
