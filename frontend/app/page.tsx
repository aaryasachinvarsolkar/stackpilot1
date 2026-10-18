"use client";

import React, { useState } from "react";
import { ToastProvider, useToast } from "@/components/ToastContainer";
import { AuthView } from "@/components/AuthView";
import { DashboardView } from "@/components/DashboardView";
import { Navbar } from "@/components/Navbar";
import { ActivityBar, SidebarView } from "@/components/ActivityBar";
import { Sidebar } from "@/project/Sidebar";
import { EditorPanel } from "@/editor/EditorPanel";
import { AICopilotPanel } from "@/chat/AICopilotPanel";
import { BottomPanel } from "@/components/BottomPanel";
import { ProjectCreateModal, NewProjectPayload } from "@/components/ProjectCreateModal";
import { IndexingProgressModal } from "@/components/IndexingProgressModal";
import { DiffReviewModal } from "@/components/DiffReviewModal";
import { CodeReviewModal, ReviewFinding } from "@/components/CodeReviewModal";
import { DocGenModal, DocType } from "@/components/DocGenModal";
import { SettingsModal } from "@/components/SettingsModal";
import { DependencyGraph } from "@/components/DependencyGraph";
import { X, LogIn, LayoutDashboard, Code2 } from "lucide-react";

function AppContent() {
  const { addToast } = useToast();

  // App View State Machine
  const [currentView, setCurrentView] = useState<"auth" | "dashboard" | "workspace">("workspace");
  const [currentUser, setCurrentUser] = useState<{ email: string; name: string } | null>({
    email: "alex@stackpilot.dev",
    name: "Alex",
  });
  const [activeProject, setActiveProject] = useState("task-manager-service");
  const [pendingProjectName, setPendingProjectName] = useState("");

  // Workspace layout states
  const [activeSidebarView, setActiveSidebarView] = useState<SidebarView>("files");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isAiPanelOpen, setIsAiPanelOpen] = useState(true);
  const [isBottomPanelOpen, setIsBottomPanelOpen] = useState(true);
  const [selectedFile, setSelectedFile] = useState("routes.py");

  // Modal open states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isIndexingModalOpen, setIsIndexingModalOpen] = useState(false);
  const [isDiffModalOpen, setIsDiffModalOpen] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [isDocGenModalOpen, setIsDocGenModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [isGraphModalOpen, setIsGraphModalOpen] = useState(false);

  // Handlers
  const handleAuthSuccess = (user: { email: string; name: string }) => {
    setCurrentUser(user);
    setCurrentView("dashboard");
    addToast({
      title: `Welcome back, ${user.name}!`,
      message: "Authenticated successfully via persistent session.",
      type: "success",
    });
  };

  const handleOpenProject = (projectId: string) => {
    setActiveProject(projectId);
    setCurrentView("workspace");
    addToast({
      title: `Workspace Loaded`,
      message: `Switched context to ${projectId}.`,
      type: "info",
    });
  };

  const handleProjectCreated = (payload: NewProjectPayload) => {
    setIsCreateModalOpen(false);
    setPendingProjectName(payload.name);
    setIsIndexingModalOpen(true);
    addToast({
      title: `Project Initialized`,
      message: `Analyzing repository source files and generating AST embeddings.`,
      type: "info",
    });
  };

  const handleIndexingComplete = () => {
    setIsIndexingModalOpen(false);
    if (pendingProjectName) {
      setActiveProject(pendingProjectName);
    }
    setCurrentView("workspace");
    addToast({
      title: `Repository Indexing Complete`,
      message: `Knowledge graph and pgvector indexes are ready.`,
      type: "success",
    });
  };

  const handleRunInBackground = () => {
    setIsIndexingModalOpen(false);
    if (pendingProjectName) {
      setActiveProject(pendingProjectName);
    }
    setCurrentView("workspace");
    addToast({
      title: `Indexing in Background`,
      message: `AST symbols and call graphs are generating concurrently.`,
      type: "info",
    });
  };

  const handleSelectFile = (file: string) => {
    setSelectedFile(file);
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-[#080c14] text-slate-100 overflow-hidden font-sans">
      {/* 1. TOP GLOBAL NAVBAR (Except when in full Auth screen, or toggleable) */}
      {currentView !== "auth" ? (
        <Navbar
          currentView={currentView === "dashboard" ? "dashboard" : "workspace"}
          onSwitchView={(v) => setCurrentView(v)}
          onToggleLeftSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          onToggleRightSidebar={() => setIsAiPanelOpen(!isAiPanelOpen)}
          onToggleBottomPanel={() => setIsBottomPanelOpen(!isBottomPanelOpen)}
          onRunTests={() => {
            if (currentView !== "workspace") setCurrentView("workspace");
            setIsBottomPanelOpen(true);
            addToast({
              title: "Running Tests in Sandbox",
              message: "Pytest executing in isolated Docker container.",
              type: "info",
            });
          }}
          onOpenCodeReview={() => setIsReviewModalOpen(true)}
          onOpenDocGen={() => setIsDocGenModalOpen(true)}
          onOpenDiffReview={() => setIsDiffModalOpen(true)}
          onOpenDependencyGraph={() => setIsGraphModalOpen(true)}
          onOpenSettings={() => setIsSettingsModalOpen(true)}
          onOpenNewProject={() => setIsCreateModalOpen(true)}
          selectedProjectName={activeProject}
          onSelectProject={(name) => {
            setActiveProject(name);
            addToast({
              title: "Project Switched",
              message: `Active workspace is now ${name}`,
              type: "info",
            });
          }}
        />
      ) : (
        /* Minimal Top Bar for Auth Mode */
        <header className="h-12 w-full border-b border-slate-800 bg-[#090d16] flex items-center justify-between px-4 z-50 text-xs">
          <div className="flex items-center gap-2 font-bold text-white">
            <span className="text-sm font-extrabold tracking-wide bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              STACKPILOT
            </span>
          </div>
          <button
            onClick={() => setCurrentView("dashboard")}
            className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-medium transition-colors"
          >
            <LayoutDashboard className="h-3.5 w-3.5" />
            <span>Skip to Dashboard</span>
          </button>
        </header>
      )}

      {/* 2. MAIN VIEW SWITCHER BODY */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* VIEW A: AUTH SCREENS */}
        {currentView === "auth" && (
          <div className="flex-1 overflow-y-auto">
            <AuthView onSuccess={handleAuthSuccess} />
          </div>
        )}

        {/* VIEW B: PROJECTS DASHBOARD */}
        {currentView === "dashboard" && (
          <div className="flex-1 overflow-y-auto">
            <DashboardView
              onOpenProject={handleOpenProject}
              onNewProject={() => setIsCreateModalOpen(true)}
            />
          </div>
        )}

        {/* VIEW C: 3-PANE IDE WORKSPACE */}
        {currentView === "workspace" && (
          <div className="flex-1 flex overflow-hidden relative">
            {/* Activity Bar (Far Left Strip) */}
            <ActivityBar
              activeView={activeSidebarView}
              setActiveView={setActiveSidebarView}
              isSidebarOpen={isSidebarOpen}
              setIsSidebarOpen={setIsSidebarOpen}
              isAiOpen={isAiPanelOpen}
              setIsAiOpen={setIsAiPanelOpen}
            />

            {/* Primary Sidebar (Explorer, Search, Git, Tests) */}
            <Sidebar
              activeView={activeSidebarView}
              selectedFile={selectedFile}
              onSelectFile={handleSelectFile}
              isOpen={isSidebarOpen}
            />

            {/* Center Area: Code Editor + Bottom Dock */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#090d16]">
              <div className="flex-1 min-h-0 overflow-hidden">
                <EditorPanel
                  selectedFile={selectedFile}
                  onSelectFile={handleSelectFile}
                  onOpenBottomPanel={() => setIsBottomPanelOpen(true)}
                />
              </div>

              {/* Bottom Dock: Sandbox Terminal, Tests, Dependencies, Problems */}
              <BottomPanel
                isOpen={isBottomPanelOpen}
                onClose={() => setIsBottomPanelOpen(false)}
                onOpenGraph={() => setIsGraphModalOpen(true)}
              />
            </div>

            {/* Right Panel: AI Copilot & Agent Planner */}
            <AICopilotPanel
              isOpen={isAiPanelOpen}
              onOpenFile={handleSelectFile}
              onOpenDiffView={() => setIsDiffModalOpen(true)}
            />
          </div>
        )}
      </div>

      {/* ---------------------------------------------------- */}
      {/* 3. OVERLAY MODALS                                     */}
      {/* ---------------------------------------------------- */}

      {/* PROJECT CREATION / IMPORT FLOW MODAL */}
      <ProjectCreateModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleProjectCreated}
      />

      {/* INDEXING PROGRESS TELEMETRY MODAL */}
      <IndexingProgressModal
        projectName={pendingProjectName || activeProject}
        isOpen={isIndexingModalOpen}
        onComplete={handleIndexingComplete}
        onRunInBackground={handleRunInBackground}
      />

      {/* DIFF / REVIEW MODAL */}
      <DiffReviewModal
        isOpen={isDiffModalOpen}
        onClose={() => setIsDiffModalOpen(false)}
        onAcceptAll={() => {
          setIsDiffModalOpen(false);
          addToast({
            title: "All Diffs Accepted",
            message: "Applied 2 modified files to working tree branch.",
            type: "success",
          });
        }}
        onRunTests={() => {
          setIsDiffModalOpen(false);
          if (currentView !== "workspace") setCurrentView("workspace");
          setIsBottomPanelOpen(true);
          addToast({
            title: "Sandbox Verification",
            message: "Running test suites against applied changes in Docker sandbox.",
            type: "info",
          });
        }}
      />

      {/* CODE REVIEW FINDINGS MODAL */}
      <CodeReviewModal
        isOpen={isReviewModalOpen}
        onClose={() => setIsReviewModalOpen(false)}
        onJumpToFile={(file, line) => {
          setIsReviewModalOpen(false);
          if (currentView !== "workspace") setCurrentView("workspace");
          setSelectedFile(file.split("/").pop() || file);
          addToast({
            title: "Jumped to Finding",
            message: `Focused ${file} at line ${line}`,
            type: "info",
          });
        }}
        onApplySuggestion={(finding: ReviewFinding) => {
          addToast({
            title: "Suggestion Applied",
            message: `Fixed: ${finding.title}`,
            type: "success",
          });
        }}
      />

      {/* DOCUMENTATION GENERATOR MODAL */}
      <DocGenModal
        isOpen={isDocGenModalOpen}
        onClose={() => setIsDocGenModalOpen(false)}
        onSaveToProject={(docType: DocType, content: string) => {
          setIsDocGenModalOpen(false);
          addToast({
            title: "Documentation Saved",
            message: `Created markdown file for ${docType.toUpperCase()} in project repository.`,
            type: "success",
          });
        }}
      />

      {/* SETTINGS & PROJECT MEMORY MODAL */}
      <SettingsModal
        isOpen={isSettingsModalOpen}
        onClose={() => setIsSettingsModalOpen(false)}
        projectName={activeProject}
        onReindex={() => {
          setIsSettingsModalOpen(false);
          setIsIndexingModalOpen(true);
        }}
      />

      {/* INTERACTIVE DEPENDENCY GRAPH FULL MODAL */}
      {isGraphModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md select-none animate-in fade-in duration-150">
          <div className="w-full max-w-6xl h-[88vh] bg-surface border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden relative">
            <DependencyGraph
              onClose={() => setIsGraphModalOpen(false)}
              onSelectNode={(path) => {
                setIsGraphModalOpen(false);
                if (currentView !== "workspace") setCurrentView("workspace");
                setSelectedFile(path.split("/").pop() || path);
              }}
            />
          </div>
        </div>
      )}
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
