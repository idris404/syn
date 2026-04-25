import { TrialDetailClient } from "@/components/TrialDetailClient";

export default async function TrialPage({
  params,
}: {
  params: Promise<{ nct_id: string }>;
}) {
  const { nct_id } = await params;
  return <TrialDetailClient nctId={nct_id} />;
}
