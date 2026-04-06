"use client";

import { BatchList } from "@/features/inventory/components/batch-list";

interface BatchesTabProps {
  moleculeId: string;
}

export function BatchesTab({ moleculeId }: BatchesTabProps) {
  return <BatchList moleculeId={moleculeId} />;
}
