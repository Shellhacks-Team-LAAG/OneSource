// src/lib/api.ts
const RAW_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
// strip any trailing slashes to avoid //ask
const API_BASE = RAW_BASE.replace(/\/+$/, "");

export type AskResponse = {
  trace_id: string;
  answer: string;
  citations: { label: string; url: string }[];
  freshness: string;
  confidence: number;
  policy_banner: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
  const r = await fetch(url, init);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${url} ${r.status} ${text}`);
  }
  return r.json() as Promise<T>;
}

export async function askApi(query: string): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

export type ConnectionsStatus = { slack: boolean; drive: boolean; github: boolean };

export async function getConnections(): Promise<ConnectionsStatus> {
  return request<ConnectionsStatus>("/connections");
}

export async function startAuthorize(provider: "slack" | "github" | "drive") {
  return request<{ authorize_url: string; state?: string }>(`/connections/${provider}/authorize`, {
    method: "POST",
  });
}

export async function getTrace<T = unknown>(id: string): Promise<T> {
  return request<T>(`/trace/${id}`);
}

// helpful to confirm in console
console.log("[VITE_API_BASE]", RAW_BASE, "→ using", API_BASE);
