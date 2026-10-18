# STACKPILOT — User Guide & Manual

Welcome to STACKPILOT! This guide explains how to use the web interface to accelerate your development workflows.

---

## 1. Navigating the Workspace

The STACKPILOT interface is organized into a streamlined, high-productivity 3-pane layout:
1. **Left Pane (File Explorer)**: Browse directory trees, view file sizes, search files across the repository, and inspect project statistics.
2. **Center Pane (Monaco Code Editor)**: Full-featured code editor with syntax highlighting, tabbed navigation, code modification preview, and unified diff viewer.
3. **Right Pane (AI Assistant & Planner)**: Interactive chat panel showing context-grounded answers, citations, task plans, tool execution logs, and approval buttons.

---

## 2. Typical Workflow

### Step 1: Open or Import a Project
- Click **"New Project"** on the dashboard.
- Select a local directory or upload a repository archive.
- STACKPILOT automatically analyzes and indexes the codebase.

### Step 2: Ask Questions Grounded in Context
- Type any question in the AI Chat (e.g. *"How does user authorization work in this service?"*).
- STACKPILOT queries vector embeddings, retrieves relevant functions and imports, and answers with clickable file citations.

### Step 3: Request Code Changes
- Submit a request: *"Add pagination support to the get_users endpoint and update unit tests"*.
- The AI creates a numbered **Implementation Plan**.
- Review the plan and click **"Approve Plan"**.

### Step 4: Review Diffs & Execute Tests
- The agent inspects code, modifies related files, and executes the test suite in the Docker sandbox.
- Inspect the unified diff viewer (green additions, red deletions).
- Click **"Accept Changes"** to commit the modifications to Git.
