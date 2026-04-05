import { BatchDetail } from "@/features/inventory/components/batch-detail";

export default async function BatchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <BatchDetail batchId={id} />;
}
