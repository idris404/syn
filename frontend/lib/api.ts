import { AgentRun, Figure, KpiData, PaperSummary, Trial, TrialSearchResult } from "@/lib/types";

const BASE = "/api";

function buildUrl(path: string, params?: Record<string, string>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value) search.set(key, value);
    }
  }
  const query = search.toString();
  return `${BASE}${path}${query ? `?${query}` : ""}`;
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const res = await fetch(buildUrl(path, params), { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  searchTrials: (q: string, phase?: string, status?: string, limit = 20) =>
    get<{ results: TrialSearchResult[] }>("/trials/search", {
      q,
      phase: phase || "",
      status: status || "",
      limit: String(limit),
    }),
  getTrial: (nctId: string) => get<Trial>(`/trials/${nctId}`),
  getTrialPapers: (nctId: string) => get<PaperSummary[]>(`/trials/${nctId}/papers`),
  getFigures: (uploadId: string) => get<Figure[]>(`/papers/${uploadId}/figures`),
  getRuns: () => get<{ runs: AgentRun[]; active_run_id?: string }>("/agents/runs"),
  getRun: (runId: string) => get<AgentRun>(`/agents/runs/${runId}`),
  triggerRun: () => post<{ run_id: string; status: string }>("/agents/run", { targets: null }),
  uploadPdf: (file: File, vision = false) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/ingest/pdf${vision ? "/vision" : ""}`, {
      method: "POST",
      body: form,
    }).then((r) => {
      if (!r.ok) throw new Error(`API error ${r.status}: upload`);
      return r.json();
    });
  },
  getKpis: () => get<KpiData>("/kpis"),
};
