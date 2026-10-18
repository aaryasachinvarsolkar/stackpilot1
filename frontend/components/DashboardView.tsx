"use client";

import React, { useState, useEffect } from "react";
import {
  FolderGit2,
  Plus,
  Search,
  Clock,
  FileCode,
  GitCommit,
  CheckCircle2,
  FolderOpen,
  ArrowRight,
  Sparkles,
  Layers,
  ChevronRight,
  Filter,
} from "lucide-react";

export interface ProjectItem {
  id: string;
  name: string;
  description: string;
  languages: string[];
  lastIndexed: string;
  lastCommit: string;
  fileCount: number;
  openAgentTasks: number;
}

import { getProjects } from "@/lib/api";

interface DashboardViewProps {
  onOpenProject: (projectId: string) => void;
  onNewProject: () => void;
}

const DEFAULT_PROJECTS: ProjectItem[] = [
  {
    id: "task-manager-service",
    name: "task-manager-service",
    description: "Distributed task orchestrator with FastAPI backend and async worker pool",
    languages: ["Python", "SQLAlchemy", "AsyncPG"],
    lastIndexed: "2 hours ago",
    lastCommit: "a8f3b9c (feat: add health probes)",
    fileCount: 24,
    openAgentTasks: 1,
  },
  {
    id: "auth-microservice",
    name: "auth-microservice",
    description: "JWT OAuth authentication service with rate limiting and session memory",
    languages: ["TypeScript", "Node.js", "Express"],
    lastIndexed: "1 day ago",
    lastCommit: "4e21a7d (fix: token expiration clamp)",
    fileCount: 38,
    openAgentTasks: 0,
  },
  {
    id: "e-commerce-api",
    name: "e-commerce-api",
    description: "High-throughput product catalog and payment checkout pipeline",
    languages: ["Go", "PostgreSQL", "Docker"],
    lastIndexed: "3 days ago",
    lastCommit: "9c12e5f (chore: update pgvector schema)",
    fileCount: 52,
    openAgentTasks: 2,
  },
];

export function DashboardView({ onOpenProject, onNewProject }: DashboardViewProps) {
  const [search, setSearch] = useState("");
  const [projects, setProjects] = useState<ProjectItem[]>(DEFAULT_PROJECTS);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadProjects() {
      setLoading(true);
      const data = await getProjects();
      if (data && data.length > 0) {
        const mapped: ProjectItem[] = data.map((p) => ({
          id: p.name, // using name or id
          name: p.name,
          description: p.description || "Microservice workspace with FastAPI backend",
          languages: p.languages && p.languages.length > 0 ? p.languages : ["Python"],
          lastIndexed: p.last_indexed || "Recently",
          lastCommit: "HEAD (feat: synced)",
          fileCount: p.file_count || 12,
          openAgentTasks: 1,
        }));
        setProjects(mapped);
      }
      setLoading(false);
    }
    loadProjects();
  }, []);

  const filteredProjects = projects.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase()) ||
    p.languages.some((l) => l.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 select-none">
      {/* Top Banner / Actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">Your Projects</h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Manage your indexed repositories, launch agentic workspaces, and inspect codebases.
          </p>
        </div>

        <button
          onClick={onNewProject}
          className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 shadow-glow transition-all"
        >
          <Plus className="h-4 w-4" />
          <span>New Project</span>
        </button>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="h-4 w-4 text-slate-500 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search projects by name, description, or stack..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-900/80 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-white placeholder:text-slate-500 outline-none focus:border-indigo-500 transition-colors"
          />
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span>{filteredProjects.length} projects found</span>
        </div>
      </div>

      {/* Projects Grid or Empty State */}
      {filteredProjects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredProjects.map((project) => (
            <div
              key={project.id}
              onClick={() => onOpenProject(project.id)}
              className="p-5 rounded-2xl bg-surface/40 hover:bg-surface/70 border border-slate-800 hover:border-indigo-500/50 backdrop-blur-xl transition-all cursor-pointer group flex flex-col justify-between space-y-4 shadow-sm"
            >
              <div className="space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 group-hover:scale-105 transition-transform">
                    <FolderGit2 className="h-5 w-5" />
                  </div>

                  {project.openAgentTasks > 0 ? (
                    <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300 font-mono text-[10px] font-semibold flex items-center gap-1">
                      <Sparkles className="h-3 w-3 text-amber-400" />
                      {project.openAgentTasks} Agent Task
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-[10px] font-semibold flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> Ready
                    </span>
                  )}
                </div>

                <div>
                  <h3 className="text-base font-bold text-white group-hover:text-indigo-300 transition-colors flex items-center gap-1.5">
                    <span>{project.name}</span>
                    <ChevronRight className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity text-indigo-400" />
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {project.description}
                  </p>
                </div>

                {/* Stack Badges */}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {project.languages.map((lang, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-slate-300 text-[10px] font-mono"
                    >
                      {lang}
                    </span>
                  ))}
                </div>
              </div>

              {/* Stats Footer */}
              <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <div className="flex items-center gap-1.5" title="Files in project">
                  <FileCode className="h-3.5 w-3.5 text-slate-400" />
                  <span>{project.fileCount} files</span>
                </div>
                <div className="flex items-center gap-1.5" title="Last indexed">
                  <Clock className="h-3.5 w-3.5 text-slate-400" />
                  <span>{project.lastIndexed}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Empty State */
        <div className="p-12 rounded-2xl bg-surface/30 border border-slate-800 text-center flex flex-col items-center justify-center space-y-4 max-w-lg mx-auto">
          <div className="h-12 w-12 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500">
            <FolderOpen className="h-6 w-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">No projects found</h3>
            <p className="text-xs text-slate-400 mt-1">
              {search
                ? `No projects match "${search}". Try checking for typos or clear your search query.`
                : "You don't have any projects indexed in your STACKPILOT workspace yet."}
            </p>
          </div>
          <button
            onClick={() => {
              if (search) setSearch("");
              else onNewProject();
            }}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 transition-all shadow-glow"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{search ? "Clear Search" : "Create or Import Your First Project"}</span>
          </button>
        </div>
      )}
    </div>
  );
}
