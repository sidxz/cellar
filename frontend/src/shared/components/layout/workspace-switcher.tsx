"use client";

import { HexLensLogo } from "@/shared/components/hex-lens-logo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/shared/components/ui/sidebar";
import { useAuthz } from "@sentinel-auth/nextjs";
import { Check, FlaskConical } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

interface WorkspaceOption {
  id: string;
  name: string;
  slug: string;
  role: string;
}

/** Read stored IdP token + provider from AuthzLocalStorageStore keys. */
function getStoredCredentials(): { idpToken: string; provider: string } | null {
  if (typeof window === "undefined") return null;
  const idpToken = localStorage.getItem("sentinel_idp_token");
  const provider = localStorage.getItem("sentinel_idp_provider");
  if (!idpToken || !provider) return null;
  return { idpToken, provider };
}

export function WorkspaceSwitcher() {
  const { user, client } = useAuthz();
  const { isMobile } = useSidebar();
  const [workspaces, setWorkspaces] = useState<WorkspaceOption[]>([]);
  const [switching, setSwitching] = useState(false);

  const currentWorkspace = user?.workspaceSlug ?? "Workspace";
  const currentWorkspaceId = user?.workspaceId;

  const loadWorkspaces = useCallback(async () => {
    if (!client) return;
    try {
      const creds = getStoredCredentials();
      if (!creds) return;

      const response = await client.resolve(creds.idpToken, creds.provider);
      if (response.workspaces) {
        setWorkspaces(response.workspaces);
      }
    } catch {
      // Silent fail — show current workspace only
    }
  }, [client]);

  const switchWorkspace = useCallback(
    async (workspaceId: string) => {
      if (!client || switching) return;
      setSwitching(true);
      try {
        const creds = getStoredCredentials();
        if (!creds) return;

        await client.selectWorkspace(creds.idpToken, creds.provider, workspaceId);
        window.location.href = "/";
      } catch {
        setSwitching(false);
      }
    },
    [client, switching],
  );

  // Load workspaces when dropdown opens
  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <div className="flex aspect-square size-8 items-center justify-center">
                <HexLensLogo className="size-7" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">ChemCellar</span>
                <span className="truncate text-xs uppercase tracking-wider text-muted-foreground">
                  {currentWorkspace}
                </span>
              </div>
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            align="start"
            side={isMobile ? "bottom" : "right"}
            sideOffset={4}
          >
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Workspaces
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {workspaces.length > 0 ? (
              workspaces.map((ws) => (
                <DropdownMenuItem
                  key={ws.id}
                  disabled={switching}
                  onClick={() => {
                    if (ws.id !== currentWorkspaceId) switchWorkspace(ws.id);
                  }}
                >
                  <FlaskConical className="mr-2 size-4" />
                  <div className="flex flex-1 items-center justify-between">
                    <span className="truncate">{ws.name}</span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] text-muted-foreground">{ws.role}</span>
                      {ws.id === currentWorkspaceId && <Check className="size-3.5 text-primary" />}
                    </div>
                  </div>
                </DropdownMenuItem>
              ))
            ) : (
              <DropdownMenuItem disabled>
                <FlaskConical className="mr-2 size-4" />
                <span>{currentWorkspace}</span>
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
