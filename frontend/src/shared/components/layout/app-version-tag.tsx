"use client";

import { useAppConfig } from "@/shared/lib/app-config";

/**
 * Compact, always-visible UI version tag for the sidebar footer.
 * Reads the baked UI version from runtime config — no network call.
 */
export function AppVersionTag() {
  const { uiVersion } = useAppConfig();
  return (
    <span className="text-[11px] font-medium tracking-wide text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden">
      UI v{uiVersion}
    </span>
  );
}
