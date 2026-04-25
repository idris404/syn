import { Badge } from "@/components/ui/badge";
import { Figure } from "@/lib/types";

interface Props {
  figures: Figure[];
}

export function FigureGallery({ figures }: Props) {
  if (!figures.length) {
    return <p className="text-sm text-[var(--syn-muted)]">Aucune figure extraite pour ce contenu.</p>;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {figures.map((fig) => {
        const structured = fig.structured_data as {
          hazard_ratio?: number;
          p_value?: number;
        };
        return (
          <div key={fig.id} className="rounded-lg border border-[var(--syn-border)] p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <Badge className="status-default">{fig.figure_type.replace("_", " ")}</Badge>
              <span className="text-xs text-[var(--syn-muted)]">
                Confiance: {Math.round(fig.confidence_score * 100)}%
              </span>
            </div>
            <p className="text-sm text-[var(--syn-muted)]">{fig.raw_interpretation.slice(0, 300)}...</p>
            {fig.figure_type === "kaplan_meier" && structured?.hazard_ratio ? (
              <div className="mt-2 rounded bg-[#0c0f17] p-2 font-mono text-xs">
                HR = {structured.hazard_ratio}
                {structured.p_value ? ` | p = ${structured.p_value}` : ""}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
