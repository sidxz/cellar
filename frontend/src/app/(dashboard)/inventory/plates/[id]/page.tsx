"use client";

import { use } from "react";
import { PlateDetail } from "@/features/inventory/components/plate-detail";

export default function PlateDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <PlateDetail plateId={id} />;
}
