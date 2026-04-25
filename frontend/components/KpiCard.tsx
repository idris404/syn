import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  label: string;
  value: string | number;
  hint?: string;
}

export function KpiCard({ label, value, hint }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-[var(--syn-muted)]">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        {hint ? <p className="mt-2 text-xs text-[var(--syn-muted)]">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
