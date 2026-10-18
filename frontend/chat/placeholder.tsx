"use client";

import React, { useState } from "react";
import { Bot, Send, Sparkles, FileText, CheckCircle2, Play, Terminal } from "lucide-react";

interface Message {
  role: "assistant" | "user";
  text: string;
  citations?: string[];
  plan?: string[];
}

export function ChatPlaceholder() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "I am ready to assist with your codebase. Ask architecture questions, generate tests, or request multi-file modifications.",
    },
    {
      role: "user",
      text: "Where is the detailed health check route located?",
    },
    {
      role: "assistant",
      text: "The detailed health check endpoint is implemented in `detailed_health()` which verifies database connectivity and returns system metadata.",
      citations: ["app/api/routes.py:20-33", "app/database/connection.py:27-44"],
    },
  ]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg: Message = { role: "user", text: input };
    const botReply: Message = {
      role: "assistant",
      text: `Processing query across AST index and vector retrieval: "${input}"`,
      citations: ["app/api/routes.py:1-45"],
    };

    setMessages((prev) => [...prev, userMsg, botReply]);
    setInput("");
  };

  return (
    <div className="h-full flex flex-col bg-surface/50 border border-slate-800/80 rounded-xl overflow-hidden backdrop-blur-md">
      {/* Chat Header */}
      <div className="p-3 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <Bot className="h-3.5 w-3.5 text-indigo-400" />
          </div>
          <span className="text-xs font-bold uppercase tracking-wider text-slate-200">AI ASSISTANT</span>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          RAG ACTIVE
        </span>
      </div>

      {/* Messages Feed */}
      <div className="flex-1 p-3 overflow-y-auto space-y-3">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`flex flex-col gap-1.5 ${
              m.role === "user" ? "items-end" : "items-start"
            }`}
          >
            <div
              className={`max-w-[90%] p-3 rounded-xl text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-indigo-600 text-white rounded-br-none shadow-glow"
                  : "bg-slate-900/80 text-slate-200 border border-slate-800/80 rounded-bl-none"
              }`}
            >
              {m.text}
            </div>

            {/* Citations */}
            {m.citations && m.citations.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-0.5">
                {m.citations.map((c, cIdx) => (
                  <span
                    key={cIdx}
                    className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800/70 border border-slate-700/60 text-indigo-300 hover:text-white cursor-pointer transition-colors"
                  >
                    <FileText className="h-2.5 w-2.5" />
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Input Box */}
      <form onSubmit={handleSend} className="p-2 border-t border-slate-800/80 bg-slate-900/40 flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question or request code changes..."
          className="flex-1 bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder:text-slate-500 outline-none focus:border-indigo-500 transition-colors"
        />
        <button
          type="submit"
          className="p-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors shadow-glow"
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  );
}
