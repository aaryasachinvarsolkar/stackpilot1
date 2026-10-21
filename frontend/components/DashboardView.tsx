"use client";

import React, { useState, useEffect, useCallback } from "react";
import { FolderGit2, Plus, Search, FileCode, FolderOpen, ChevronRight, AlertTriangle, RefreshCw, FlaskConical } from "lucide-react";
import { getProjects } from "@/lib/api";
import { SAMPLE_FILES, SAMPLE_PROJECT } from "@/lib/sampleScenario";
import type { ProjectRef } from "@/components/WorkspaceView";

// Real projects come only from the backend. The sample project below is a labelled, built-in demo
// scenario; it is never stored in the database and is always shown separately.
export interface ProjectItem {
  id: string;
  name: string;
  description: string;
  fileCount: number;
  workspaceExists: boolean;
  origin: string;
}

interface DashboardViewProps {
  onOpenProject: (project: ProjectRef) => void;
  onNewProject: () => void;
  refreshKey: number;
}

export function DashboardView({ onOpenProject, onNewProject, refreshKey }: DashboardViewProps) {
  const [search, setSearch] = useState("");
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProjects();
      setProjects(
        data.map((p) => ({
          id: p.id,
          name: p.name,
          description: p.description ?? "",
          fileCount: p.file_count,
          workspaceExists: p.workspace_exists,
          origin: p.origin,
        }))
      );
    } catch (err) {
      setProjects([]);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects, refreshKey]);

  const q = search.toLowerCase();
  const filteredProjects = projects.filter((p) => p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q));

  return (
    <div className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10 select-none">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">Projects</h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1" data-testid="dashboard-subtitle">
            Prototype of a cross-layer dependency and change-impact tool. Your projects are listed from the backend; the dependency graph and impact analysis currently run only on the labelled sample scenario.
          </p>
        </div>
        <button
          onClick={onNewProject}
          data-testid="new-project"
          className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 shadow-glow transition-all"
        >
          <Plus className="h-4 w-4" />
          <span>New Project</span>
        </button>
      </div>

      {/* ------------------------ sample scenario (always available, even offline) ------------------------ */}
      <section className="space-y-3" data-testid="sample-section">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-white">Sample scenario</h2>
          <span className="px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-400/40 text-violet-200 text-[10px] font-semibold tracking-wide">SAMPLE DATA</span>
        </div>
        <div
          onClick={() => onOpenProject({ kind: "sample" })}
          data-testid="sample-card"
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpenProject({ kind: "sample" })}
          className="p-5 rounded-2xl bg-violet-500/5 hover:bg-violet-500/10 border border-violet-400/30 hover:border-violet-400/60 transition-all cursor-pointer group flex flex-col sm:flex-row sm:items-center gap-4"
        >
          <div className="h-11 w-11 rounded-xl bg-violet-500/15 border border-violet-400/30 flex items-center justify-center text-violet-300 shrink-0">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-white flex items-center gap-1.5">
              {SAMPLE_PROJECT.title}
              <ChevronRight className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity text-violet-300" />
            </h3>
            <p className="text-xs text-slate-300 mt-1 leading-relaxed">{SAMPLE_PROJECT.description}</p>
            <p className="text-[11px] text-slate-500 mt-1.5">Explore the dependency graph, run a change-impact analysis and preview a modification. {SAMPLE_FILES.length} sample files, illustrative data only.</p>
          </div>
          <span className="px-4 py-2 rounded-xl bg-violet-600 group-hover:bg-violet-500 text-white font-semibold text-xs shrink-0">Open the sample</span>
        </div>
      </section>

      {/* ------------------------ real projects ------------------------ */}
      <section className="space-y-4" data-testid="real-section">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-white">Your projects</h2>
          <div className="flex items-center gap-3 flex-1 sm:justify-end">
            <div className="relative flex-1 max-w-md">
              <Search className="h-4 w-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search projects by name or description..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-slate-900/80 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-white placeholder:text-slate-500 outline-none focus:border-indigo-500 transition-colors"
              />
            </div>
            <span className="text-xs text-slate-400 whitespace-nowrap" data-testid="project-count">
              {loading ? "Loading..." : error ? "Backend unavailable" : `${filteredProjects.length} found`}
            </span>
          </div>
        </div>

        {loading ? (
          <div data-testid="projects-loading" className="p-10 text-center text-xs text-slate-400">Loading projects from the backend...</div>
        ) : error ? (
          <div data-testid="projects-error" className="p-8 rounded-2xl bg-rose-950/20 border border-rose-500/30 text-center flex flex-col items-center space-y-3 max-w-lg mx-auto">
            <AlertTriangle className="h-6 w-6 text-rose-400" />
            <h3 className="text-base font-bold text-white">Could not load projects from the backend</h3>
            <p className="text-xs text-slate-300">{error}. Is the API running on 127.0.0.1:8000? No sample projects are shown in its place (the sample scenario above still works).</p>
            <button onClick={loadProjects} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs flex items-center gap-2">
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Retry</span>
            </button>
          </div>
        ) : filteredProjects.length > 0 ? (
          <div data-testid="projects-grid" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredProjects.map((project) => (
              <div
                key={project.id}
                data-testid="project-card"
                data-name={project.name}
                role="button"
                tabIndex={0}
                onClick={() => onOpenProject({ kind: "real", name: project.name })}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpenProject({ kind: "real", name: project.name })}
                className="p-5 rounded-2xl bg-surface/40 hover:bg-surface/70 border border-slate-800 hover:border-indigo-500/50 backdrop-blur-xl transition-all cursor-pointer group flex flex-col justify-between space-y-4 shadow-sm"
              >
                <div className="space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 group-hover:scale-105 transition-transform">
                      <FolderGit2 className="h-5 w-5" />
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {project.workspaceExists ? (
                        <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-[10px] font-semibold">Folder found</span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-[10px] font-semibold">Folder missing on disk</span>
                      )}
                      {project.origin === "unclassified" && (
                        <span
                          title="This project predates origin tracking. Its description and other stored metadata were not verified."
                          className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-600 text-slate-300 font-mono text-[10px] font-semibold"
                          data-testid="unverified-chip"
                        >
                          Unverified metadata
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="text-base font-bold text-white group-hover:text-indigo-300 transition-colors flex items-center gap-1.5">
                      <span>{project.name}</span>
                      <ChevronRight className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity text-indigo-400" />
                    </h3>
                    <p className={`text-xs mt-1 line-clamp-2 leading-relaxed ${project.origin === "unclassified" ? "text-slate-500 italic" : "text-slate-400"}`}>
                      {project.description || <span>No description</span>}
                    </p>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                  <div className="flex items-center gap-1.5" title="Files currently on disk (ignored folders excluded)">
                    <FileCode className="h-3.5 w-3.5 text-slate-400" />
                    <span>{project.fileCount} files</span>
                  </div>
                  <span title="How this project was created. 'unclassified' means unknown.">origin: {project.origin}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-10 rounded-2xl bg-surface/30 border border-slate-800 text-center flex flex-col items-center justify-center space-y-4 max-w-lg mx-auto" data-testid="projects-empty">
            <div className="h-12 w-12 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500">
              <FolderOpen className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">No projects found</h3>
              <p className="text-xs text-slate-400 mt-1">
                {search ? `No projects match "${search}".` : "No projects are registered in the backend yet. Create one with New Project, or open the sample scenario above."}
              </p>
            </div>
            {search && (
              <button onClick={() => setSearch("")} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs">Clear search</button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
