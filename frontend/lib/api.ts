const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface ProjectApiItem {
  id: string;
  name: string;
  description: string | null;
  root_path: string;
  is_indexed: boolean;
  languages: string[];
  file_count: number;
  workspace_exists: boolean;
  origin: string;
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
  /** SHA-256 (hex) of the exact bytes on disk when this was read. A save must send it back as base_sha256. */
  sha256: string;
}

export interface CitationItem {
  file_path: string;
  line_start: number;
  line_end: number;
  symbol?: string;
  status?: string;
  excerpt_id?: string;
  file_sha256?: string;
  range_sha256?: string;
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
  status: string;
  grounding?: Record<string, any>;
}

export interface ChatStatusData {
  provider: string;
  model: string | null;
  configured: boolean;
  consent: boolean;
  can_send: boolean;
  reason: string | null;
}

export interface ChatHistoryItem {
  id: string;
  sender: "user" | "assistant" | "system";
  content: string;
  citations: CitationItem[];
  plan_steps: PlanStepItem[];
  timestamp: string;
  status?: string | null;
  grounding?: Record<string, any>;
}

/**
 * Fetch all registered projects from the backend.
 * Failures are thrown (never replaced by an empty list or sample data) so the UI can say so.
 */
export async function getProjects(): Promise<ProjectApiItem[]> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/projects`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new Error("The backend could not be reached");
  }
  if (!res.ok) throw new Error(`The backend answered HTTP ${res.status}`);
  return await res.json();
}

// ---------------------------------------------------------------------------------------------
// Strict helpers: always report the real HTTP status and the server's own error message, and
// never substitute demo data. Used by the workspace and the create-project dialog.
// ---------------------------------------------------------------------------------------------

export interface ApiResult<T> {
  ok: boolean;
  status: number; // 0 = the backend could not be reached
  data?: T;
  message?: string;
}

async function problemFrom(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const d = body?.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && typeof d.message === "string") return d.message;
    if (Array.isArray(d) && d.length) return d.map((x: { msg?: string }) => x.msg ?? "invalid value").join("; ");
  } catch {
    /* body was not JSON */
  }
  return `The backend answered HTTP ${res.status}`;
}

async function call<T>(url: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store", ...init });
  } catch {
    return { ok: false, status: 0, message: "The backend could not be reached" };
  }
  if (!res.ok) return { ok: false, status: res.status, message: await problemFrom(res) };
  return { ok: true, status: res.status, data: (await res.json()) as T };
}

export const fetchProject = (nameOrId: string) =>
  call<ProjectApiItem>(`${API_BASE_URL}/api/projects/${encodeURIComponent(nameOrId)}`);

export const fetchTree = (nameOrId: string) =>
  call<TreeNode[]>(`${API_BASE_URL}/api/projects/${encodeURIComponent(nameOrId)}/files/tree`);

export const fetchFile = (nameOrId: string, path: string) =>
  call<FileContentData>(`${API_BASE_URL}/api/projects/${encodeURIComponent(nameOrId)}/files/content?path=${encodeURIComponent(path)}`);

export const createProject = (payload: { name: string; description?: string; template: string }) =>
  call<ProjectApiItem>(`${API_BASE_URL}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, source_type: "blank" }),
  });

export const uploadProjectZip = (formData: FormData) =>
  call<ProjectApiItem>(`${API_BASE_URL}/api/projects/upload`, {
    method: "POST",
    body: formData,
  });

export const importGitProject = (payload: { name: string; git_url: string; branch?: string; description?: string }) =>
  call<ProjectApiItem>(`${API_BASE_URL}/api/projects/git`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export interface GraphNode {
  id: string;
  label: string;
  path: string;
  type: string;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
}

export interface ProjectGraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  summary: string;
}

export const getProjectGraph = (nameOrId: string) =>
  call<ProjectGraphData>(`${API_BASE_URL}/api/projects/${encodeURIComponent(nameOrId)}/graph`);

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

export interface FileSaveData {
  status: string;
  path: string;
  bytes_written: number;
  /** SHA-256 (hex) of the content the server just wrote; the base_sha256 for the next save. */
  sha256: string;
}

/**
 * Update an EXISTING file, if it is still the version the caller loaded: `baseSha256` is the `sha256`
 * returned when the content was read. The server answers 409 when the file changed on disk since then,
 * 428 when the hash is missing, 404 when the file is gone. Failures carry the HTTP status and the
 * server's own message (also path rejected, file too large, backend unreachable) instead of being swallowed.
 */
export const saveFileContent = (nameOrId: string, path: string, content: string, baseSha256: string) =>
  call<FileSaveData>(`${API_BASE_URL}/api/projects/${encodeURIComponent(nameOrId)}/files/content`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content, base_sha256: baseSha256 }),
  });

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
    const res = await fetch(`${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/chat`, {
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

/**
 * Fetch AI chat provider readiness and consent status.
 */
export async function getChatStatus(projectId: string): Promise<ChatStatusData | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/chat/status`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Failed to fetch chat status for ${projectId}:`, err);
    return null;
  }
}

/**
 * Fetch chat message history for a project.
 */
export async function getChatHistory(projectId: string): Promise<ChatHistoryItem[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/chat/history`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Failed to fetch chat history for ${projectId}:`, err);
    return [];
  }
}

/**
 * Clear chat history for a project.
 */
export async function clearChatHistory(projectId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/chat/history`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    });
    return res.ok;
  } catch (err) {
    console.error(`Failed to clear chat history for ${projectId}:`, err);
    return false;
  }
}


// ---------------------------------------------------------------------------------------------
// Guided changes: analyze the impact, propose exact edits, apply only what the user approved.
// ---------------------------------------------------------------------------------------------

export interface ImpactFile {
  path: string;
  category: "direct" | "indirect";
  why: string;
  editable: boolean;
  not_editable_reason: string | null;
}

export interface PlanStep {
  id?: number;
  action: "modify" | "create";
  path: string;
  what: string;
}

export interface ImpactReport {
  status: "analyzed" | "not_in_context";
  summary: string;
  risk: "low" | "medium" | "high" | null;
  risk_reasons: string[];
  affected_files: ImpactFile[];
  plan: PlanStep[];
  skipped_steps: { path: string; reason: string }[];
  questions: string[];
  excerpts_used: number;
}

export interface ProposedFile {
  path: string;
  is_new: boolean;
  explanation: string;
  diff: string;
  added: number;
  removed: number;
}

export interface ChangeProposal {
  proposal_id: string;
  status: string;
  summary: string;
  files: ProposedFile[];
  rejected: { path: string; reason: string }[];
}

const changesUrl = (projectId: string, tail: string) =>
  `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/changes/${tail}`;

const postJson = (url: string, body: unknown): RequestInit & { url: string } => ({
  url,
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function postChange<T>(projectId: string, tail: string, body: unknown) {
  const { url, ...init } = postJson(changesUrl(projectId, tail), body);
  return call<T>(url, init);
}

export const analyzeChange = (projectId: string, request: string) =>
  postChange<ImpactReport>(projectId, "analyze", { request });

export const proposeChange = (projectId: string, request: string, notes: string, steps: PlanStep[]) =>
  postChange<ChangeProposal>(projectId, "propose", {
    request,
    notes,
    steps: steps.map(({ action, path, what }) => ({ action, path, what })),
  });

export const applyChange = (projectId: string, proposalId: string, paths: string[]) =>
  postChange<{ proposal_id: string; status: string; applied: string[] }>(projectId, "apply", {
    proposal_id: proposalId,
    paths,
  });

export const revertChange = (projectId: string, proposalId: string) =>
  postChange<{ proposal_id: string; status: string; reverted: string[] }>(projectId, "revert", {
    proposal_id: proposalId,
  });

// ---------------------------------------------------------------------------------------------
// Live preview: run a project's web page in the browser (read-only, sandboxed, nothing executes server-side).
// ---------------------------------------------------------------------------------------------

export interface PreviewInfo {
  kind: "static" | "server" | "none";
  /** The page shown first, e.g. "frontend/index.html". Null unless kind is "static". */
  entry: string | null;
  candidates: { path: string }[];
  hints: string[];
  needs_backend: boolean;
  message: string;
}

/** Use the project's ID (not its name): preview addresses never resolve a project by name. */
export const getPreviewInfo = (projectId: string) =>
  call<PreviewInfo>(`${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/preview-info`);

/** Address of one project file as served for the preview. `version` only makes the browser fetch it again. */
export function previewFileUrl(projectId: string, path: string, version?: number): string {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  const base = `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/preview/${safePath}`;
  return version === undefined ? base : `${base}?v=${version}`;
}

// ---------------------------------------------------------------------------------------------
// Run the whole project: start/stop the project's own backend. Needs the owner's switch
// (ALLOW_RUNNING_PROJECT_CODE) in the backend environment; the status says so when it is off.
// ---------------------------------------------------------------------------------------------

export type RunState = "idle" | "preparing" | "installing" | "starting" | "running" | "stopped" | "failed";

export interface RunStatus {
  allowed: boolean;
  blocked_reason: string | null;
  state: RunState;
  message: string;
  plan: {
    kind: string;
    source: string;
    install: string | null;
    start: string;
    app_ports: number[];
    auto_reload: boolean;
    fixed_port: number | null;
    /** Programs the commands need besides Python, e.g. ["go"] or ["npm"]. */
    requires: string[];
    /** Things found in the project's files that will probably stop it from running. */
    warnings: string[];
  } | null;
  plan_problem: string | null;
  /** Programs the plan needs that are not installed on this computer, and what to do about it. */
  missing_tools: string[];
  missing_tools_help: string | null;
  port: number | null;
  started_at: string | null;
  log: string[];
}

const runUrl = (projectId: string, tail = "") => `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/run${tail}`;

export const getRunStatus = (projectId: string) => call<RunStatus>(runUrl(projectId));
export const startRun = (projectId: string) => call<RunStatus>(runUrl(projectId, "/start"), { method: "POST" });
export const stopRun = (projectId: string) => call<RunStatus>(runUrl(projectId, "/stop"), { method: "POST" });
export const restartRun = (projectId: string) => call<RunStatus>(runUrl(projectId, "/restart"), { method: "POST" });

/** The running project's own address as served through this app (for a project that has no static page of its own). */
export function runningAppUrl(projectId: string, version?: number): string {
  const base = `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/app/`;
  return version === undefined ? base : `${base}?v=${version}`;
}
