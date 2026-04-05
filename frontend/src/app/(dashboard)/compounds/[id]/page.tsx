import { CompoundDetail } from "@/features/chemical-registration";

export default async function CompoundPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CompoundDetail compoundId={id} />;
}
