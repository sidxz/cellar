"use client";

import { PlateGroupPage } from "@/features/inventory/components/plate-group-page";
import { use } from "react";

export default function PlateGroupDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <PlateGroupPage groupId={id} />;
}
