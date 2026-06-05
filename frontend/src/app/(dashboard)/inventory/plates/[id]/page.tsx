"use client";

import { PlateDetail } from "@/features/inventory/components/plate-detail";
import { use } from "react";

export default function PlateDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <PlateDetail plateId={id} />;
}
