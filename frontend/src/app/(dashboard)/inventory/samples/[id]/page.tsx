import { SampleDetail } from "@/features/inventory/components/sample-detail";

export default async function SampleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SampleDetail sampleId={id} />;
}
