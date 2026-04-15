"use client";

import { useDataSources } from "@/features/workspace-config/hooks/use-data-sources";

export function useCddEnabled() {
  const { data: sources, isLoading } = useDataSources();

  if (isLoading) return { enabled: false, loading: true };

  const hasActiveCdd = sources?.some(
    (ds) => ds.source_type === "cdd_vault" && ds.is_active
  );

  return { enabled: !!hasActiveCdd, loading: false };
}
