export interface HealthResponse {
  status: string;
  database: string;
  database_type: string;
  environment: string;
  debug: boolean;
  version: string;
  timestamp: string;
}

export interface InfoResponse {
  name: string;
  tagline: string;
  version: string;
  status: string;
  capabilities: string[];
  active_providers: {
    llm: string;
    embedding: string;
  };
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`, {
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    return {
      status: "unreachable",
      database: "unknown",
      database_type: "none",
      environment: "unknown",
      debug: false,
      version: "0.1.0",
      timestamp: new Date().toISOString(),
    };
  }
}

export async function fetchSystemInfo(): Promise<InfoResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/info`, {
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    return {
      name: "STACKPILOT",
      tagline: "AI-Powered Software Development Platform",
      version: "0.1.0",
      status: "operational",
      capabilities: [
        "Codebase Indexing (AST)",
        "Semantic RAG Retrieval",
        "Agent Planning & Tool Calling",
        "Multi-File Modification & Diff Review",
        "Sandboxed Execution & Testing",
        "Automated Debugging Loops",
        "Git Integration",
      ],
      active_providers: {
        llm: "mock",
        embedding: "mock",
      },
    };
  }
}
