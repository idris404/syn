"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AgentRunCard } from "@/components/AgentRunCard";
import { AlertBanner } from "@/components/AlertBanner";
import { KpiCard } from "@/components/KpiCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Toaster } from "@/components/ui/toaster";
import { useToastStore } from "@/components/ui/use-toast";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/lib/api";
import { AgentRun, KpiData, TrialSearchResult, WsMessage } from "@/lib/types";

export default function HomePage() {
  const [kpis, setKpis] = useState<KpiData | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [recentTrials, setRecentTrials] = useState<TrialSearchResult[]>([]);
  const [alert, setAlert] = useState<WsMessage | null>(null);
  const { items, toast } = useToastStore();

  useEffect(() => {
    api.getKpis().then(setKpis).catch(() => null);
    api.getRuns().then((res) => setRuns(res.runs || [])).catch(() => null);
    api.searchTrials("cancer", undefined, undefined, 5)
      .then((res) => setRecentTrials(res.results || []))
      .catch(() => null);
  }, []);

  useWebSocket((msg) => {
    if (msg.type === "run_complete") {
      setAlert(msg);
      toast({ title: "Run terminé", description: msg.title || "Nouveau rapport prêt" });
      api.getRuns().then((res) => setRuns(res.runs || [])).catch(() => null);
      api.getKpis().then(setKpis).catch(() => null);
    }
  });

  const lastRun = useMemo(() => runs[0], [runs]);

  async function triggerRun() {
    try {
      const res = await api.triggerRun();
      toast({ title: "Run lancé", description: `Run ID: ${res.run_id}` });
      api.getRuns().then((r) => setRuns(r.runs || [])).catch(() => null);
    } catch (e) {
      toast({ title: "Erreur", description: e instanceof Error ? e.message : "Impossible de lancer le run" });
    }
  }

  return (
    <main className="space-y-6">
      <Toaster items={items} />
      <AlertBanner message={alert} onClose={() => setAlert(null)} />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Total Essais" value={kpis?.total_trials ?? "-"} />
        <KpiCard label="En recrutement" value={kpis?.recruiting_trials ?? "-"} />
        <KpiCard label="Papers indexés" value={kpis?.total_papers ?? "-"} />
        <KpiCard label="Rapports générés" value={kpis?.total_reports ?? "-"} />
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">Dernier run agent</h2>
          {lastRun ? <AgentRunCard run={lastRun} /> : <p className="text-sm text-[var(--syn-muted)]">Aucun run disponible.</p>}
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Actions rapides</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button onClick={triggerRun}>Lancer un run</Button>
            <div>
              <Link href="/ingest" className="text-sm text-[var(--syn-accent)] hover:underline">
                Aller vers l&apos;upload PDF
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Essais récents</h2>
        <Card>
          <CardContent className="pt-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>NCT ID</TableHead>
                  <TableHead>Titre</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Phase</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentTrials.map((trial) => (
                  <TableRow key={trial.nct_id}>
                    <TableCell>
                      <Link href={`/trials/${trial.nct_id}`} className="text-[var(--syn-accent)] hover:underline">
                        {trial.nct_id}
                      </Link>
                    </TableCell>
                    <TableCell>{trial.title || "-"}</TableCell>
                    <TableCell>{trial.status || "-"}</TableCell>
                    <TableCell>{trial.phase || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
