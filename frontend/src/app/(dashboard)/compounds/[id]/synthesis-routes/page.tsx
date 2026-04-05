import { SynthesisRouteList } from "@/features/chemical-registration/components/synthesis-route-list";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SynthesisRouteList moleculeId={id} />;
}
