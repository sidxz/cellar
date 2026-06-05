"use client";

import { DataSourceDetail } from "@/features/workspace-config/components/data-source-detail";
import { useParams } from "next/navigation";

export default function DataSourceDetailPage() {
  const params = useParams<{ id: string }>();
  return <DataSourceDetail dataSourceId={params.id} />;
}
