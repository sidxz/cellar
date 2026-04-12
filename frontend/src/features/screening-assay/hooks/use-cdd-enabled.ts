"use client";

import { useApiKeys } from "@/features/workspace-config/hooks/use-api-keys";
import { useWorkspaceSettings } from "@/features/workspace-config/hooks/use-workspace-settings";

export function useCddEnabled() {
  const { data: apiKeys, isLoading: keysLoading } = useApiKeys();
  const { data: settings, isLoading: settingsLoading } = useWorkspaceSettings();

  const loading = keysLoading || settingsLoading;

  if (loading) return { enabled: false, loading: true };

  const hasCddKey = apiKeys?.some(
    (k) => k.key_name === "cdd_vault" && k.is_active
  );
  const hasCddVaultId = !!settings?.cdd_vault_id;

  return { enabled: !!hasCddKey && hasCddVaultId, loading: false };
}
