"use client";

import { PageHeader } from "@/shared/components/page-header";
import { Alert, AlertDescription } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { useAppConfig } from "@/shared/lib/app-config";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useSyncTargets } from "../hooks/use-targets";
import { TargetList } from "./target-list";

/** Admin → Targets: the mirror table plus the one explicit gesture that
 *  changes it — a full pull from prot-cellar (no limit; the backend pages
 *  through prot-cellar's cursor). */
export function AdminTargetsPage() {
  const { protCellarUrl } = useAppConfig();
  const sync = useSyncTargets();

  return (
    <>
      <PageHeader
        title="Targets"
        subtitle="Biological targets are owned by Prot-Cellar and mirrored here read-only."
      >
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <a href={`${protCellarUrl}/targets`} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="mr-2 h-4 w-4" />
              Manage in Prot-Cellar
            </a>
          </Button>
          <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
            <RefreshCw className={`mr-2 h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} />
            {sync.isPending ? "Syncing…" : "Sync from Prot-Cellar"}
          </Button>
        </div>
      </PageHeader>

      {sync.isSuccess && (
        <p className="mt-2 text-muted-foreground text-sm" data-testid="sync-report">
          {sync.data.fetched} fetched — {sync.data.created} created · {sync.data.updated} updated ·{" "}
          {sync.data.skipped} unchanged
        </p>
      )}
      {sync.isError && (
        <Alert variant="destructive" className="mt-2">
          <AlertDescription>{sync.error.message}</AlertDescription>
        </Alert>
      )}

      <div className="mt-6">
        <TargetList />
      </div>
    </>
  );
}
