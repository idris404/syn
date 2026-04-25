import { ReportPageClient } from "@/components/ReportPageClient";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ run_id: string }>;
}) {
  const { run_id } = await params;
  return <ReportPageClient runId={run_id} />;
}
