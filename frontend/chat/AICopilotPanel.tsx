"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Bot,
  Send,
  Sparkles,
  FileCode,
  RotateCw,
  Trash2,
  User,
} from "lucide-react";
import {
  postChatMessage,
  getChatHistory,
  clearChatHistory,
  getChatStatus,
  CitationItem,
  ChatStatusData,
} from "@/lib/api";
import {
  normalizeStatus,
  statusLabel,
  statusBadgeClasses,
  citationDisplay,
  citationsHeading,
} from "@/lib/chatGrounding";
import { ChangeAssistant } from "@/chat/ChangeAssistant";
import type { ChangeFlow } from "@/lib/useChangeFlow";

interface AICopilotPanelProps {
  projectId: string;
  onOpenFile: (file: string, lineStart?: number, lineEnd?: number) => void;
  onOpenDiffView: () => void;
  isOpen: boolean;
  /** The guided-change flow, owned by the workspace so the Impact and Preview tabs share it. */
  flow: ChangeFlow;
}

interface MessageItem {
  id: string;
  sender: "user" | "assistant" | "system";
  content: string;
  citations?: CitationItem[];
  timestamp: string;
  status?: string | null;
  grounding?: Record<string, any>;
}

export function AICopilotPanel({ projectId, onOpenFile, onOpenDiffView, isOpen, flow }: AICopilotPanelProps) {
  const [activeTab, setActiveTab] = useState<"agent" | "chat" | "review">("chat");
  const [promptInput, setPromptInput] = useState("");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [chatStatus, setChatStatus] = useState<ChatStatusData | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const isSample = projectId === "orders-platform" || projectId === "sample";

  // Load chat provider status and history when project changes
  useEffect(() => {
    async function loadData() {
      if (!projectId) return;

      // Check provider readiness and consent status from the backend
      const st = await getChatStatus(projectId);
      setChatStatus(st);

      // Fetch stored message history from the backend
      const history = await getChatHistory(projectId);
      if (history && history.length > 0) {
        setMessages(
          history.map((m) => ({
            id: m.id,
            sender: m.sender,
            content: m.content,
            citations: m.citations || [],
            timestamp: m.timestamp,
            status: m.status,
            grounding: m.grounding,
          }))
        );
        return;
      }

      // Initial state: no scripted sample answers. All answers require a backend model.
      setMessages([
        {
          id: "msg-init",
          sender: "assistant",
          content: isSample
            ? "This is the sample project. Scripted sample answers have been removed: answers come only from a model configured on the backend."
            : "No conversation yet. Replies only come from a model configured on the backend; if none is, the reply will say so.",
          citations: [],
          timestamp: new Date().toISOString(),
          status: "legacy",
        },
      ]);
    }

    loadData();
  }, [projectId, isSample]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isExecuting]);

  if (!isOpen) return null;

  const handleSendMessage = async () => {
    const text = promptInput.trim();
    if (!text || isExecuting) return;

    setPromptInput("");
    setIsExecuting(true);

    // Optimistically add user message
    const tempUserMsg: MessageItem = {
      id: `usr-${Date.now()}`,
      sender: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    // Send to backend API; never substitute invented or scripted answers
    const res = await postChatMessage(projectId, text, activeTab);
    if (!res) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: "system",
          content: "The request failed: the backend could not be reached or returned an error. Nothing was analysed.",
          timestamp: new Date().toISOString(),
          status: "error",
        },
      ]);
    } else {
      const asstMsg: MessageItem = {
        id: res.message_id || `asst-${Date.now()}`,
        sender: "assistant",
        content: res.content,
        citations: res.citations || [],
        timestamp: res.timestamp || new Date().toISOString(),
        status: res.status,
        grounding: res.grounding,
      };
      setMessages((prev) => [...prev, asstMsg]);
    }

    setIsExecuting(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleClearChat = async () => {
    const cleared = await clearChatHistory(projectId);
    setMessages([
      {
        id: `clear-${Date.now()}`,
        sender: cleared ? "assistant" : "system",
        content: cleared
          ? "Conversation history cleared."
          : "The history could not be cleared: the backend could not be reached or returned an error.",
        timestamp: new Date().toISOString(),
        status: cleared ? "legacy" : "error",
      },
    ]);
  };

  const renderMessageCard = (m: MessageItem) => {
    const isUser = m.sender === "user";
    const isSystem = m.sender === "system";

    if (isUser) {
      return (
        <div
          key={m.id}
          className="p-3 rounded-xl border bg-indigo-950/30 border-indigo-800/40 text-right w-full space-y-1.5"
        >
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-indigo-300 justify-end">
            <span>You</span>
            <User className="h-3 w-3" />
          </div>
          <div className="text-slate-200 text-xs leading-relaxed whitespace-pre-wrap font-sans text-left">
            {m.content}
          </div>
        </div>
      );
    }

    const normStatus = normalizeStatus(m.status);
    const lbl = statusLabel(normStatus);
    const badgeClasses = statusBadgeClasses(lbl.tone);
    const citations = m.citations || [];

    return (
      <div
        key={m.id}
        className="p-3 rounded-xl border bg-slate-900/80 border-slate-800 w-full space-y-2"
      >
        <div className="flex items-center justify-between text-[11px]">
          <div className="flex items-center gap-1.5 font-semibold text-cyan-400">
            <Bot className="h-3.5 w-3.5" />
            <span>{isSystem ? "System" : "STACKPILOT Assistant"}</span>
          </div>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${badgeClasses}`}
            data-testid="message-status-badge"
            data-status={normStatus}
          >
            {lbl.text}
          </span>
        </div>

        <div className="text-slate-200 text-xs leading-relaxed whitespace-pre-wrap font-sans text-left">
          {m.content}
        </div>

        {citations.length > 0 && (
          <div className="pt-2 border-t border-slate-800/80 text-left space-y-1.5">
            <span className="text-[10px] text-slate-400 font-semibold uppercase block">
              {citationsHeading(normStatus)}
            </span>
            <div className="flex flex-wrap gap-1.5">
              {citations.map((c, idx) => {
                const disp = citationDisplay(c.status, normStatus);
                return (
                  <button
                    key={idx}
                    type="button"
                    disabled={!disp.clickable}
                    data-testid="citation-button"
                    data-citation-status={disp.status}
                    data-clickable={disp.clickable}
                    onClick={() => {
                      if (disp.clickable) {
                        onOpenFile(c.file_path, c.line_start, c.line_end);
                      }
                    }}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[10px] transition-colors ${disp.classes}`}
                    title={disp.clickable ? `Open ${c.file_path}:${c.line_start}-${c.line_end}` : `Invalid citation: ${c.file_path}`}
                  >
                    <FileCode className="h-2.5 w-2.5" />
                    <span>
                      {c.file_path}:{c.line_start}-{c.line_end}
                    </span>
                    <span className="text-[9px] opacity-80 font-sans ml-0.5">
                      ({disp.label})
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="w-80 lg:w-96 h-full bg-[#0b101b] border-l border-slate-800 flex flex-col select-none text-xs z-20">
      {/* ---------------------------------------------------- */}
      {/* 1. COPILOT HEADER & MODE SELECTOR                    */}
      {/* ---------------------------------------------------- */}
      <div className="p-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-lg bg-gradient-to-tr from-indigo-500 to-cyan-500 p-[1px] shadow-glow flex items-center justify-center">
            <div className="h-full w-full bg-slate-900 rounded-lg flex items-center justify-center">
              <Bot className="h-3.5 w-3.5 text-indigo-400" />
            </div>
          </div>
          <div className="flex flex-col">
            <span className="font-bold uppercase tracking-wider text-slate-200">AI COPILOT</span>
            <span className="text-[9px] text-slate-500 font-mono truncate max-w-[120px]">{projectId}</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <div className="flex items-center gap-0.5 p-0.5 bg-slate-900 border border-slate-800 rounded-lg">
            <button
              onClick={() => setActiveTab("chat")}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                activeTab === "chat" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
              }`}
            >
              Chat
            </button>
            <button
              onClick={() => setActiveTab("agent")}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                activeTab === "agent" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
              }`}
            >
              Agent
            </button>
            <button
              onClick={() => setActiveTab("review")}
              className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
                activeTab === "review" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
              }`}
            >
              Review
            </button>
          </div>

          <button
            onClick={handleClearChat}
            className="p-1 hover:bg-slate-800 text-slate-500 hover:text-rose-400 rounded transition-colors"
            title="Clear Chat History"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* CONTEXT & PROVIDER STATUS BAR                        */}
      {/* ---------------------------------------------------- */}
      <div className="px-3 py-1.5 bg-slate-900/60 border-b border-slate-800 flex flex-col gap-1 text-[11px]" data-testid="copilot-status">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-slate-400">
            <span
              className={`h-2 w-2 rounded-full ${
                chatStatus?.can_send
                  ? "bg-emerald-500"
                  : chatStatus?.configured
                  ? "bg-amber-500"
                  : "bg-slate-600"
              }`}
            />
            <span className="truncate max-w-[220px]">
              {chatStatus
                ? chatStatus.can_send
                  ? `Connected: ${chatStatus.provider} (${chatStatus.model || "default"})`
                  : !chatStatus.configured
                  ? `Provider not configured (${chatStatus.provider})`
                  : "Sending code to provider is disabled"
                : "Checking provider..."}
            </span>
          </div>
          {isSample && <span className="text-[9px] text-slate-400 font-mono">SCRIPTED SAMPLE REMOVED</span>}
        </div>
        <div className="text-[10px] text-slate-500 flex items-center justify-between">
          <span>Project files are not indexed yet</span>
          {chatStatus && !chatStatus.can_send && chatStatus.reason && (
            <span className="text-amber-400/80 truncate max-w-[150px]" title={chatStatus.reason}>
              {chatStatus.reason}
            </span>
          )}
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 2. TAB: CHAT (PRIMARY CONVERSATION STREAM)           */}
      {/* ---------------------------------------------------- */}
      {activeTab === "chat" && (
        <div className="flex-1 flex flex-col p-3 space-y-3 overflow-y-auto">
          {messages.map(renderMessageCard)}

          {isExecuting && (
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5 flex items-center gap-2 text-indigo-300">
              <RotateCw className="h-3.5 w-3.5 animate-spin text-indigo-400" />
              <span className="text-xs">Waiting for the backend...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 3. TAB: AGENT (GUIDED CHANGES: IMPACT, REVIEW, APPLY) */}
      {/* ---------------------------------------------------- */}
      {activeTab === "agent" && (
        <>
          <ChangeAssistant
            flow={flow}
            canSend={!!chatStatus?.can_send}
            blockedReason={chatStatus?.reason}
            onOpenFile={(file) => onOpenFile(file)}
          />
          <div className="mx-3 mb-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5" data-testid="not-available">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-300">Not available yet</div>
            <ul className="text-[11px] text-slate-400 space-y-1 list-disc pl-4">
              <li>Running tests or commands in a sandbox</li>
              <li>Git commit and push</li>
              <li>Creating, renaming or deleting files (only existing files can be edited)</li>
            </ul>
          </div>
        </>
      )}

      {/* ---------------------------------------------------- */}
      {/* 4. TAB: CODE REVIEW AUDIT                            */}
      {/* ---------------------------------------------------- */}
      {activeTab === "review" && (
        <div className="flex-1 p-3 space-y-3 overflow-y-auto">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="font-bold uppercase tracking-wider text-slate-300">CODE REVIEW</span>
            <span className="text-slate-400 font-mono text-[10px] uppercase" data-testid="review-not-available">
              Not available yet
            </span>
          </div>
          <p className="text-slate-400 text-xs leading-relaxed">
            Automated code review has not been built yet. No review was run on {projectId}, so there are no findings to show.
          </p>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 5. PROMPT INPUT BAR (FUNCTIONAL & CONNECTED)         */}
      {/* ---------------------------------------------------- */}
      {activeTab === "chat" && (
        <div className="p-2 border-t border-slate-800 bg-[#080c14]">
          <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 focus-within:border-indigo-500 transition-colors">
            <input
              type="text"
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message (replies need a model configured on the backend)..."
              className="flex-1 bg-transparent border-none outline-none text-xs text-white placeholder:text-slate-600 font-sans"
            />
            <button
              onClick={handleSendMessage}
              disabled={!promptInput.trim() || isExecuting}
              className={`p-1.5 rounded-md transition-colors shadow-glow flex items-center justify-center ${
                promptInput.trim() && !isExecuting
                  ? "bg-indigo-600 hover:bg-indigo-500 text-white cursor-pointer"
                  : "bg-slate-800 text-slate-500 cursor-not-allowed"
              }`}
              title="Submit request (Enter)"
            >
              <Send className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
