"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { AgentRun } from "@/lib/types";
import { statusClass } from "@/lib/utils";

export default function ReportsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [pollingRunId, setPollingRunId] = useState<string | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    api.getRuns().then((res) => setRuns(res.runs || [])).catch(() => null);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function triggerRun() {
    const res = await api.triggerRun();
    setPollingRunId(res.run_id);
    timerRef.current = setInterval(async () => {
      const run = await api.getRun(res.run_id);
      if (run.status === "done" || run.status === "failed") {
        if (timerRef.current) clearInterval(timerRef.current);
        setPollingRunId(null);
        api.getRuns().then((r) => setRuns(r.runs || [])).catch(() => null);
      }
    }, 5000);
  }

  return (
    <main className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Historique des rapports</h1>
        <Button onClick={triggerRun}>Nouveau rapport</Button>
      </div>

      {pollingRunId ? (
        <p className="text-sm text-[var(--syn-muted)]">Run en cours: {pollingRunId}</p>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Runs agents</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Titre</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Findings</TableHead>
                <TableHead>Durée</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => (
                <TableRow key={run.run_id}>
                  <TableCell>{run.started_at ? new Date(run.started_at).toLocaleString("fr-FR") : "-"}</TableCell>
                  <TableCell>
                    <Link href={`/reports/${run.run_id}`} className="text-[var(--syn-accent)] hover:underline">
                      {run.report_title || run.run_id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge className={statusClass(run.status)}>{run.status}</Badge>
                  </TableCell>
                  <TableCell>{run.key_findings?.length ?? 0}</TableCell>
                  <TableCell>{run.duration_seconds ? `${run.duration_seconds}s` : "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}
