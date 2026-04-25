import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrialSearchResult } from "@/lib/types";
import { statusClass } from "@/lib/utils";

interface Props {
  trial: TrialSearchResult;
}

export function TrialCard({ trial }: Props) {
  return (
    <Link href={`/trials/${trial.nct_id}`}>
      <Card className="h-full transition hover:border-[var(--syn-accent)]/60">
        <CardHeader>
          <CardTitle className="line-clamp-2 text-base">{trial.title || trial.nct_id}</CardTitle>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge className={statusClass(trial.status)}>{trial.status || "UNKNOWN"}</Badge>
            <Badge className="status-default">{trial.phase || "N/A"}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--syn-muted)]">{trial.sponsor || "Sponsor non renseigné"}</p>
          <p className="mt-2 text-xs text-[var(--syn-muted)]">
            Score: {typeof trial.semantic_score === "number" ? trial.semantic_score.toFixed(3) : "-"}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}
