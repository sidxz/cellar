import { ShipmentDetail } from "@/features/inventory/components/shipment-detail";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ShipmentDetail shipmentId={id} />;
}
