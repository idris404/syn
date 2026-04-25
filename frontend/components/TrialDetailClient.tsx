"use client";

import { useEffect, useMemo, useState } from "react";

import { FigureGallery } from "@/components/FigureGallery";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { Figure, PaperSummary, Trial } from "@/lib/types";
import { statusClass } from "@/lib/utils";

interface Props {
  nctId: string;
}

export function TrialDetailClient({ nctId }: Props) {
  const [trial, setTrial] = useState<Trial | null>(null);
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [figures, setFigures] = useState<Figure[]>([]);

  useEffect(() => {
    api.getTrial(nctId).then(setTrial).catch(() => setTrial(null));
    api.getTrialPapers(nctId).then(setPapers).catch(() => setPapers([]));
  }, [nctId]);

  useEffect(() => {
    const uploadIds = papers.map((p) => p.upload_id).filter(Boolean) as string[];
    if (!uploadIds.length) {
      setFigures([]);
      return;
    }
    Promise.all(uploadIds.map((id) => api.getFigures(id).catch(() => [])))
      .then((results) => setFigures(results.flat()))
      .catch(() => setFigures([]));
  }, [papers]);

  const title = useMemo(() => trial?.title || nctId, [trial, nctId]);

  return (
    <main className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="mt-2 flex gap-2">
          <Badge className={statusClass(trial?.status)}>{trial?.status || "UNKNOWN"}</Badge>
          <Badge className="status-default">{trial?.phase || "N/A"}</Badge>
        </div>
      </div>

      <Tabs defaultValue="info">
        <TabsList>
          <TabsTrigger value="info">Informations</TabsTrigger>
          <TabsTrigger value="papers">Publications</TabsTrigger>
          <TabsTrigger value="figures">Figures</TabsTrigger>
        </TabsList>

        <TabsContent value="info">
          <Card>
            <CardHeader>
              <CardTitle>Détails essai</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-[var(--syn-muted)]">
              <p><span className="text-[var(--syn-text)]">NCT ID:</span> {trial?.nct_id}</p>
              <p><span className="text-[var(--syn-text)]">Sponsor:</span> {trial?.sponsor || "-"}</p>
              <p><span className="text-[var(--syn-text)]">Enrollment:</span> {trial?.enrollment ?? "-"}</p>
              <p><span className="text-[var(--syn-text)]">Start:</span> {trial?.start_date || "-"}</p>
              <p><span className="text-[var(--syn-text)]">Completion:</span> {trial?.completion_date || "-"}</p>
              <p><span className="text-[var(--syn-text)]">Conditions:</span> {trial?.conditions?.join(", ") || "-"}</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="papers">
          <Card>
            <CardHeader>
              <CardTitle>Publications associées</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[360px]">
                <div className="space-y-3">
                  {papers.map((paper) => (
                    <div key={paper.id} className="rounded-md border border-[var(--syn-border)] p-3">
                      <p className="font-medium">{paper.title || paper.id}</p>
                      <p className="mt-1 text-sm text-[var(--syn-muted)]">{paper.abstract || "Aucun abstract."}</p>
                    </div>
                  ))}
                  {!papers.length ? <p className="text-sm text-[var(--syn-muted)]">Aucune publication trouvée.</p> : null}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="figures">
          <Card>
            <CardHeader>
              <CardTitle>Figures extraites</CardTitle>
            </CardHeader>
            <CardContent>
              <FigureGallery figures={figures} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </main>
  );
}
