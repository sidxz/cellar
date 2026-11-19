"use client";

import { useDataSources } from "@/features/workspace-config/hooks/use-data-sources";

export function useCddEnabled() {
  const { data: sources, isLoading } = useDataSources();

  if (isLoading) return { enabled: false, loading: true, source: undefined };

  const source = sources?.find((ds) => ds.source_type === "cdd_vault" && ds.is_active);

  return { enabled: !!source, loading: false, source };
}
