import { SampleRequestDetail } from "@/features/inventory/components/sample-request-detail";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SampleRequestDetail requestId={id} />;
}
