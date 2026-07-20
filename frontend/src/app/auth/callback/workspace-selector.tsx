"use client";

import type { AuthzWorkspaceSelectorProps } from "@sentinel-auth/nextjs";
import { useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { rememberWorkspace, rememberedWorkspace } from "@/shared/lib/auth/workspace-memory";

type Decision = { kind: "pending" } | { kind: "picker" } | { kind: "auto"; id: string };

export function WorkspaceSelector({
  workspaces,
  onSelect,
  isLoading,
}: AuthzWorkspaceSelectorProps) {
  const [decision, setDecision] = useState<Decision>({ kind: "pending" });

  // Skip the picker when the remembered workspace is still available —
  // "Switch workspace" in the header menu forgets it and brings the picker back.
  // One-time decision made in an effect: localStorage is client-only, so a
  // useState initializer would cause a hydration mismatch.
  useEffect(() => {
    if (decision.kind !== "pending" || isLoading) return;
    const remembered = rememberedWorkspace();
    if (remembered && workspaces.some((ws) => ws.id === remembered)) {
      setDecision({ kind: "auto", id: remembered });
      onSelect(remembered);
    } else {
      setDecision({ kind: "picker" });
    }
  }, [decision.kind, isLoading, workspaces, onSelect]);

  if (decision.kind !== "picker") {
    const ws = decision.kind === "auto" ? workspaces.find((w) => w.id === decision.id) : null;
    return (
      <div>
        <h2 className="text-sm font-medium text-muted-foreground">
          {ws ? `Entering ${ws.name}…` : "Signing in..."}
        </h2>
        <div className="mt-4 space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-sm font-medium text-muted-foreground">Select workspace to continue</h2>
      <div className="mt-4 space-y-2">
        {workspaces.map((ws) => (
          <Button
            key={ws.id}
            variant="outline"
            className="w-full justify-start rounded-[11px]"
            disabled={isLoading}
            onClick={() => {
              rememberWorkspace(ws.id);
              onSelect(ws.id);
            }}
          >
            <span className="truncate">{ws.name}</span>
            <span className="ml-auto text-xs text-muted-foreground">{ws.role}</span>
          </Button>
        ))}
      </div>
    </div>
  );
}
