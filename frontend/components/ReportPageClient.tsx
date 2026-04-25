"use client";

import { useEffect, useState } from "react";

import { ReportViewer } from "@/components/ReportViewer";
import { api } from "@/lib/api";
import { AgentRun } from "@/lib/types";

interface Props {
  runId: string;
}

export function ReportPageClient({ runId }: Props) {
  const [run, setRun] = useState<AgentRun | null>(null);

  useEffect(() => {
    api.getRun(runId).then(setRun).catch(() => setRun(null));
  }, [runId]);

  if (!run) return <p className="text-sm text-[var(--syn-muted)]">Chargement du rapport...</p>;

  return <ReportViewer run={run} />;
}
