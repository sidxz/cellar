import { ProtocolDetail } from "@/features/screening-assay";

export default async function ProtocolPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ProtocolDetail protocolId={id} />;
}
