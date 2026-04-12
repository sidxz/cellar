"use client";

import { useApiKeys } from "@/features/workspace-config/hooks/use-api-keys";
import { useWorkspaceSettings } from "@/features/workspace-config/hooks/use-workspace-settings";

export function useVaultEnabled() {
  const { data: apiKeys, isLoading: keysLoading } = useApiKeys();
  const { data: settings, isLoading: settingsLoading } = useWorkspaceSettings();

  const loading = keysLoading || settingsLoading;

  if (loading) return { enabled: false, loading: true };

  const hasVaultKey = apiKeys?.some(
    (k) => k.key_name === "external_vault" && k.is_active
  );
  const hasVaultId = !!settings?.external_vault_id;

  return { enabled: !!hasVaultKey && hasVaultId, loading: false };
}
