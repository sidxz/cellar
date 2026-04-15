"use client";

import { useParams } from "next/navigation";
import { DataSourceDetail } from "@/features/workspace-config/components/data-source-detail";

export default function DataSourceDetailPage() {
  const params = useParams<{ id: string }>();
  return <DataSourceDetail dataSourceId={params.id} />;
}
