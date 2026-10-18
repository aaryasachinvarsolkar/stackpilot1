"use client";

import React from "react";
import {
  Files,
  Search,
  GitBranch,
  PlayCircle,
  Bot,
  Settings,
  Shield,
  Layers,
} from "lucide-react";

export type SidebarView = "files" | "search" | "git" | "tests";

interface ActivityBarProps {
  activeView: SidebarView;
  setActiveView: (view: SidebarView) => void;
  isSidebarOpen: boolean;
  setIsSidebarOpen: (open: boolean) => void;
  isAiOpen: boolean;
  setIsAiOpen: (open: boolean) => void;
}

export function ActivityBar({
  activeView,
  setActiveView,
  isSidebarOpen,
  setIsSidebarOpen,
  isAiOpen,
  setIsAiOpen,
}: ActivityBarProps) {
  const handleItemClick = (view: SidebarView) => {
    if (activeView === view && isSidebarOpen) {
      setIsSidebarOpen(false);
    } else {
      setActiveView(view);
      setIsSidebarOpen(true);
    }
  };

  const navItems: { id: SidebarView; icon: any; label: string; badge?: string }[] = [
    { id: "files", icon: Files, label: "Explorer" },
    { id: "search", icon: Search, label: "Codebase Semantic Search" },
    { id: "git", icon: GitBranch, label: "Source Control", badge: "2" },
    { id: "tests", icon: PlayCircle, label: "Sandbox Test Runner" },
  ];

  return (
    <div className="w-12 h-full bg-[#080c14] border-r border-slate-800 flex flex-col justify-between items-center py-2 select-none z-30">
      {/* Top Activity Icons */}
      <div className="flex flex-col items-center gap-1 w-full">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = isSidebarOpen && activeView === item.id;

          return (
            <button
              key={item.id}
              onClick={() => handleItemClick(item.id)}
              className={`relative w-10 h-10 flex items-center justify-center rounded-lg transition-colors group ${
                isActive
                  ? "text-indigo-400 bg-indigo-500/10"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              }`}
              title={item.label}
            >
              {isActive && (
                <div className="absolute left-0 top-1.5 bottom-1.5 w-[3px] bg-indigo-500 rounded-r" />
              )}
              <Icon className="h-5 w-5" />
              {item.badge && (
                <span className="absolute top-1.5 right-1.5 px-1 min-w-[14px] h-[14px] rounded-full bg-indigo-600 text-[9px] font-bold text-white flex items-center justify-center">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Bottom Icons */}
      <div className="flex flex-col items-center gap-1 w-full">
        <button
          onClick={() => setIsAiOpen(!isAiOpen)}
          className={`relative w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${
            isAiOpen
              ? "text-cyan-400 bg-cyan-500/10"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
          }`}
          title="Toggle AI Agent Panel"
        >
          <Bot className="h-5 w-5" />
        </button>

        <button
          className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 transition-colors"
          title="Settings"
        >
          <Settings className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
