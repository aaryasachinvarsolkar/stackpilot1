"use client";

import React, { useState } from "react";
import { Folder, FolderOpen, FileCode, Search, ChevronRight, ChevronDown, Plus, RefreshCw } from "lucide-react";

interface FileNode {
  name: string;
  type: "file" | "folder";
  children?: FileNode[];
}

const SAMPLE_TREE: FileNode[] = [
  {
    name: "app",
    type: "folder",
    children: [
      {
        name: "api",
        type: "folder",
        children: [{ name: "routes.py", type: "file" }, { name: "__init__.py", type: "file" }],
      },
      {
        name: "database",
        type: "folder",
        children: [{ name: "connection.py", type: "file" }, { name: "session.py", type: "file" }],
      },
      {
        name: "models",
        type: "folder",
        children: [{ name: "base.py", type: "file" }],
      },
      { name: "config.py", type: "file" },
      { name: "main.py", type: "file" },
    ],
  },
  {
    name: "tests",
    type: "folder",
    children: [{ name: "test_health.py", type: "file" }, { name: "conftest.py", type: "file" }],
  },
  { name: "requirements.txt", type: "file" },
  { name: "Dockerfile", type: "file" },
];

export function ProjectExplorerPlaceholder() {
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({
    app: true,
    api: true,
    tests: false,
  });
  const [selectedFile, setSelectedFile] = useState("routes.py");

  const toggleFolder = (name: string) => {
    setOpenFolders((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const renderTree = (nodes: FileNode[], path = "") => {
    return nodes.map((node) => {
      const currentPath = `${path}/${node.name}`;
      if (node.type === "folder") {
        const isOpen = !!openFolders[node.name];
        return (
          <div key={currentPath} className="select-none">
            <div
              onClick={() => toggleFolder(node.name)}
              className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800/60 cursor-pointer text-xs text-slate-300 transition-colors"
            >
              {isOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
              )}
              {isOpen ? (
                <FolderOpen className="h-3.5 w-3.5 text-indigo-400" />
              ) : (
                <Folder className="h-3.5 w-3.5 text-indigo-400" />
              )}
              <span className="font-mono">{node.name}</span>
            </div>
            {isOpen && node.children && (
              <div className="pl-4 border-l border-slate-800/80 ml-2 mt-0.5">
                {renderTree(node.children, currentPath)}
              </div>
            )}
          </div>
        );
      }

      const isSelected = selectedFile === node.name;
      return (
        <div
          key={currentPath}
          onClick={() => setSelectedFile(node.name)}
          className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-xs font-mono transition-colors ${
            isSelected
              ? "bg-indigo-600/20 text-indigo-300 font-semibold"
              : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
          }`}
        >
          <FileCode className="h-3.5 w-3.5 text-slate-500" />
          <span>{node.name}</span>
        </div>
      );
    });
  };

  return (
    <div className="h-full flex flex-col bg-surface/50 border border-slate-800/80 rounded-xl overflow-hidden backdrop-blur-md">
      {/* Explorer Header */}
      <div className="p-3 border-b border-slate-800/80 flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-300">EXPLORER</span>
        <div className="flex items-center gap-1">
          <button className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200">
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Quick Search */}
      <div className="p-2 border-b border-slate-800/80">
        <div className="flex items-center gap-2 px-2 py-1 bg-slate-900/60 border border-slate-800 rounded-lg text-xs text-slate-400">
          <Search className="h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search files..."
            className="bg-transparent border-none outline-none text-xs text-slate-200 w-full placeholder:text-slate-600 font-mono"
          />
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 p-2 overflow-y-auto space-y-0.5">
        <div className="text-[11px] font-semibold text-slate-500 px-2 py-1 uppercase tracking-wider">
          WORKSPACE FILES
        </div>
        {renderTree(SAMPLE_TREE)}
      </div>
    </div>
  );
}
