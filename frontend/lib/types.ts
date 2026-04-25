export interface Trial {
  id: string;
  nct_id: string;
  title: string | null;
  status: string | null;
  phase: string | null;
  sponsor: string | null;
  conditions: string[] | null;
  interventions: Array<{ type: string; name: string }> | null;
  primary_outcomes: Array<{ measure: string; timeFrame: string }> | null;
  enrollment: number | null;
  start_date: string | null;
  completion_date: string | null;
}

export interface TrialSearchResult {
  id: string;
  nct_id: string;
  title: string | null;
  status: string | null;
  phase: string | null;
  sponsor: string | null;
  conditions: string[] | null;
  enrollment: number | null;
  start_date: string | null;
  completion_date: string | null;
  semantic_score?: number | null;
}

export interface AgentRun {
  run_id: string;
  started_at?: string;
  status:
    | "planning"
    | "researching"
    | "analyzing"
    | "writing"
    | "publishing"
    | "done"
    | "failed"
    | "active"
    | "started"
    | "in_progress";
  report_title?: string;
  report_summary?: string;
  report_body?: string;
  key_findings?: Array<{
    finding: string;
    evidence: string;
    importance: "high" | "medium" | "low";
  }>;
  duration_seconds?: number;
  errors?: string[];
  notion_url?: string | null;
}

export interface Figure {
  id: string;
  upload_id: string;
  page_number: number;
  figure_index?: number;
  figure_type:
    | "kaplan_meier"
    | "forest_plot"
    | "bar_chart"
    | "table"
    | "scatter"
    | "unknown";
  raw_interpretation: string;
  structured_data: Record<string, unknown>;
  confidence_score: number;
}

export interface KpiData {
  total_trials: number;
  recruiting_trials: number;
  total_papers: number;
  total_reports: number;
  last_run_at: string | null;
  last_run_status: string | null;
}

export interface WsMessage {
  type: "run_complete" | "ping";
  run_id?: string;
  title?: string;
  summary?: string;
  timestamp?: string;
}

export interface PaperSummary {
  id: string;
  source: string;
  title: string | null;
  abstract: string | null;
  score?: number | null;
  external_id?: string | null;
  date?: string | null;
  authors: string[];
  url?: string | null;
  upload_id?: string | null;
}
