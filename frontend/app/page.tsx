"use client";

import React, { useCallback, useRef, useState } from "react";
import { ToastProvider, useToast } from "@/components/ToastContainer";
import { DashboardView } from "@/components/DashboardView";
import { Navbar } from "@/components/Navbar";
import { WorkspaceView, ProjectRef } from "@/components/WorkspaceView";
import { CreateProjectDialog } from "@/components/CreateProjectDialog";
import { SAMPLE_PROJECT } from "@/lib/sampleScenario";
import type { ProjectApiItem } from "@/lib/api";

function AppContent() {
  const { addToast } = useToast();
  const [view, setView] = useState<"dashboard" | "workspace">("dashboard");
  const [project, setProject] = useState<ProjectRef | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // The workspace stays mounted while the dashboard is shown, so open files and unsaved edits survive
  // switching views. Replacing it with a different project would drop them, so that asks first.
  const workspaceDirty = useRef(false);
  const handleDirtyChange = useCallback((dirty: boolean) => {
    workspaceDirty.current = dirty;
  }, []);

  const sameProject = (a: ProjectRef | null, b: ProjectRef) =>
    a !== null && a.kind === b.kind && (a.kind === "sample" || (b.kind === "real" && a.name === b.name));

  const openProject = (p: ProjectRef) => {
    if (workspaceDirty.current && !sameProject(project, p)) {
      const ok = window.confirm("You have unsaved changes in the open project. Open another project and discard them?");
      if (!ok) return;
    }
    setProject(p);
    setView("workspace");
  };

  const handleCreated = (created: ProjectApiItem) => {
    setCreateOpen(false);
    setRefreshKey((k) => k + 1);
    addToast({
      title: "Project ready",
      message: `${created.name}: ${created.file_count} file${created.file_count === 1 ? "" : "s"} in the workspace folder.`,
      type: "success",
    });
    openProject({ kind: "real", name: created.name });
  };

  const projectLabel = project ? (project.kind === "sample" ? SAMPLE_PROJECT.title : project.name) : "";

  return (
    <div className="h-screen w-screen flex flex-col bg-[#080c14] text-slate-100 overflow-hidden font-sans">
      <Navbar currentView={view} onSwitchView={setView} projectLabel={projectLabel} />

      <main className="flex-1 min-h-0 overflow-hidden">
        {view === "dashboard" && (
          <div className="h-full overflow-y-auto">
            <DashboardView onOpenProject={openProject} onNewProject={() => setCreateOpen(true)} refreshKey={refreshKey} />
          </div>
        )}

        {project && (
          <div className={view === "workspace" ? "h-full" : "hidden"}>
            <WorkspaceView
              project={project}
              onBack={() => setView("dashboard")}
              onOpenSample={() => openProject({ kind: "sample" })}
              onDirtyChange={handleDirtyChange}
            />
          </div>
        )}

        {view === "workspace" && !project && (
          <div className="h-full flex items-center justify-center p-8" data-testid="no-project-open">
            <div className="max-w-sm text-center space-y-3">
              <h2 className="text-base font-bold text-white">No project is open</h2>
              <p className="text-xs text-slate-400">Pick a project on the dashboard to open its workspace.</p>
              <button onClick={() => setView("dashboard")} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs">
                Go to projects
              </button>
            </div>
          </div>
        )}
      </main>

      <CreateProjectDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={handleCreated} />
    </div>
  );
}

export default function Home() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}
