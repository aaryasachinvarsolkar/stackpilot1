const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface ProjectApiItem {
  id: string;
  name: string;
  description: string;
  root_path: string;
  is_indexed: boolean;
  languages: string[];
  file_count: number;
  last_indexed?: string;
  created_at: string;
}

export interface TreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  language?: string;
  children?: TreeNode[];
}

export interface FileContentData {
  path: string;
  file_name: string;
  content: string;
  line_count: number;
  language: string;
}

export interface CitationItem {
  file_path: string;
  line_start: number;
  line_end: number;
  symbol?: string;
}

export interface PlanStepItem {
  id: number;
  text: string;
  tool: string;
  status: string;
}

export interface ChatResponseData {
  conversation_id: string;
  message_id: string;
  sender: string;
  content: string;
  citations: CitationItem[];
  plan_steps: PlanStepItem[];
  timestamp: string;
}

/**
 * Fetch all registered projects from the backend.
 */
export async function getProjects(): Promise<ProjectApiItem[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("Failed to fetch projects from backend, using fallback:", err);
    return [];
  }
}

/**
 * Create a new project.
 */
export async function createProjectApi(payload: {
  name: string;
  description?: string;
  source_type: "blank" | "upload" | "git";
  template?: string;
  git_url?: string;
  git_branch?: string;
}): Promise<ProjectApiItem | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to create project: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("Project creation error:", err);
    return null;
  }
}

/**
 * Fetch project file tree hierarchy.
 */
export async function getFileTree(projectId: string): Promise<TreeNode[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${projectId}/files/tree`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Failed to fetch file tree for ${projectId}:`, err);
    return [];
  }
}

/**
 * Read content of a specific file.
 */
export async function getFileContent(projectId: string, path: string): Promise<FileContentData | null> {
  try {
    const encodedPath = encodeURIComponent(path);
    const res = await fetch(`${API_BASE_URL}/api/projects/${projectId}/files/content?path=${encodedPath}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Failed to read file ${path}:`, err);
    return null;
  }
}

/**
 * Save content to a specific file.
 */
export async function saveFileContent(
  projectId: string,
  path: string,
  content: string
): Promise<{ status: string; path: string; bytes_written: number } | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${projectId}/files/content`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, content }),
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error(`Failed to save file ${path}:`, err);
    return null;
  }
}

/**
 * Send an AI chat message and receive grounded response with citations and plan steps.
 */
export async function postChatMessage(
  projectId: string,
  message: string,
  mode: "agent" | "chat" | "review" = "agent",
  conversationId?: string
): Promise<ChatResponseData | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${projectId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode,
        conversation_id: conversationId,
      }),
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("Chat API error:", err);
    return null;
  }
}
