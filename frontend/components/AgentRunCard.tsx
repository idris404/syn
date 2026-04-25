import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentRun } from "@/lib/types";
import { statusClass } from "@/lib/utils";

interface Props {
  run: AgentRun;
}

export function AgentRunCard({ run }: Props) {
  return (
    <Link href={`/reports/${run.run_id}`}>
      <Card className="transition hover:border-[var(--syn-accent)]/60">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle className="line-clamp-2 text-base">{run.report_title || "Rapport en cours"}</CardTitle>
            <Badge className={statusClass(run.status)}>{run.status}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="line-clamp-3 text-sm text-[var(--syn-muted)]">{run.report_summary || "Aucun résumé disponible."}</p>
          <p className="mt-2 text-xs text-[var(--syn-muted)]">{run.started_at ? new Date(run.started_at).toLocaleString("fr-FR") : "Date inconnue"}</p>
        </CardContent>
      </Card>
    </Link>
  );
}
