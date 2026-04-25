"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentRun } from "@/lib/types";

interface Props {
  run: AgentRun;
}

const importanceClass: Record<string, string> = {
  high: "bg-red-500/10 text-red-400",
  medium: "bg-amber-500/10 text-amber-400",
  low: "bg-slate-500/10 text-slate-300",
};

export function ReportViewer({ run }: Props) {
  return (
    <div className="space-y-6">
      <div className="no-print flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{run.report_title || "Rapport agent"}</h1>
          <p className="text-sm text-[var(--syn-muted)]">{run.report_summary || ""}</p>
        </div>
        <Button onClick={() => window.print()}>Export PDF</Button>
      </div>

      {!!run.key_findings?.length && (
        <Card>
          <CardHeader>
            <CardTitle>Findings clés</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {run.key_findings.map((finding, idx) => (
              <div key={`${finding.finding}-${idx}`} className="rounded-md border border-[var(--syn-border)] p-3">
                <div className="mb-2 flex items-center gap-2">
                  <Badge className={importanceClass[finding.importance] || importanceClass.low}>
                    {finding.importance}
                  </Badge>
                </div>
                <p className="font-medium">{finding.finding}</p>
                <p className="mt-1 text-sm text-[var(--syn-muted)]">{finding.evidence}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Rapport complet</CardTitle>
        </CardHeader>
        <CardContent className="prose prose-invert max-w-none prose-p:text-slate-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.report_body || "_Rapport indisponible._"}</ReactMarkdown>
        </CardContent>
      </Card>
    </div>
  );
}
