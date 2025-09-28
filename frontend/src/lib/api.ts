//import { ask, AskResponse } from "../lib/api";

export interface Citation {
  source: string;
  title: string;
  url: string;
  freshness: string;
}

//export interface AskResponse {
 // answer: string;
 // citations: Citation[];
 // confidence: number;
 // freshness: string;
 // trace_id: string;
//}


export type AskResponse = {
  answer: string;
  citations: Citation[];
  confidence: number;
  freshness: string;
  trace_id: string;
};

export interface TraceCandidate {
  source: string;
  doc_id: string;
  url: string;
  snippet: string;
  last_modified: string;
  authority: Record<string, any>;
  raw_score: number;
  timing_ms: number;
  redacted?: boolean;
}

export interface TraceResponse {
  trace_id: string;
  query: string;
  timestamp: string;
  fusion: {
    chosen_doc_id: string;
    confidence: number;
    rationale: string;
  };
  candidates: TraceCandidate[];
}

// Force Vite env to string
const API_BASE = import.meta.env.VITE_API_BASE as string;

// POST /ask
export async function ask(query: string): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    throw new Error(`Ask failed with status ${res.status}`);
  }
  return (await res.json()) as AskResponse;
}

// GET /trace/{id}
export async function getTrace(traceId: string): Promise<TraceResponse> {
  const res = await fetch(`${API_BASE}/trace/${encodeURIComponent(traceId)}`);
  if (!res.ok) {
    throw new Error(`Trace failed with status ${res.status}`);
  }
  return (await res.json()) as TraceResponse;
}
