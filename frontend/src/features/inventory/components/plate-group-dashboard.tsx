"use client";

import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { showError } from "@/shared/lib/toast";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { usePlateGroupTree } from "../hooks/use-plate-groups";
import { PlateGroupDialog } from "./plate-group-dialog";
import { PlateGroupTreeView } from "./plate-group-tree";
import { ROOT_STORAGE_KEY, pickRoot, subtreePlateCount } from "./plate-group-tree-utils";
import { PlateInsightsPanel } from "./plate-insights-panel";
import { RequestLoanDialog } from "./request-loan-dialog";

export function PlateGroupDashboard() {
  const router = useRouter();
  const { data: me, isError: meFailed } = useCurrentUser();
  const isAdmin = me?.is_admin === true;
  const { data: orgs } = useOrgs();
  const [orgId, setOrgId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [rootId, setRootId] = useState<string | null>(null);
  const [loanGroup, setLoanGroup] = useState<PlateGroupNode | null>(null);
  const [tab, setTab] = useHashTab("hierarchy");

  // Default the selector to my org once /me resolves; if /me failed, fall
  // back to the first org in the directory so the page still works.
  useEffect(() => {
    if (orgId !== null) return;
    if (me?.org_id) setOrgId(me.org_id);
    else if (meFailed && orgs?.length) {
      setOrgId(orgs[0].id);
      showError("Could not resolve your organization — showing the first org");
    }
  }, [orgId, me, meFailed, orgs]);

  const {
    data: tree,
    isLoading,
    error,
  } = usePlateGroupTree(orgId ?? undefined, {
    enabled: orgId !== null,
  });

  const roots = tree?.roots ?? [];

  // (Re)select the root when the org or the tree changes: remember the last
  // root per org (localStorage), falling back to the first root.
  useEffect(() => {
    if (!orgId || roots.length === 0) return;
    let remembered: string | null = null;
    try {
      remembered = window.localStorage.getItem(ROOT_STORAGE_KEY(orgId));
    } catch {
      remembered = null;
    }
    const next = pickRoot(roots, remembered, rootId);
    if (next !== rootId) setRootId(next);
  }, [orgId, roots, rootId]);

  const selectRoot = (id: string) => {
    setRootId(id);
    try {
      if (orgId) window.localStorage.setItem(ROOT_STORAGE_KEY(orgId), id);
    } catch {
      /* storage unavailable — selection is per-session only */
    }
  };
  const rootNode = roots.find((r) => r.id === rootId) ?? null;

  return (
    <div className="flex flex-col gap-4 p-6">
      <PageHeader title="Plate Groups" subtitle="Org-owned hierarchy for organizing plates">
        {roots.length > 0 ? (
          <Select value={rootId ?? ""} onValueChange={selectRoot}>
            <SelectTrigger className="w-64" aria-label="Root group" data-testid="root-group-select">
              <SelectValue placeholder="Root group" />
            </SelectTrigger>
            <SelectContent>
              {roots.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.name} ({subtreePlateCount(r)})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        {isAdmin ? (
          <Select
            value={orgId ?? ""}
            onValueChange={(v) => {
              setOrgId(v);
              setRootId(null);
            }}
          >
            <SelectTrigger className="w-56" aria-label="Organization">
              <SelectValue placeholder="Organization" />
            </SelectTrigger>
            <SelectContent>
              {(orgs ?? []).map((o) => (
                <SelectItem key={o.id} value={o.id}>
                  {o.name}
                  {me?.org_id === o.id ? " (my org)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        {tab === "hierarchy" ? (
          <Button
            data-testid="create-root-group"
            disabled={orgId === null}
            onClick={() => setCreateOpen(true)}
          >
            New group
          </Button>
        ) : null}
      </PageHeader>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="hierarchy">Hierarchy</TabsTrigger>
          <TabsTrigger value="insights">Insights</TabsTrigger>
        </TabsList>

        <TabsContent value="hierarchy" className="mt-4">
          {error ? (
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : "Failed to load groups"}
            </p>
          ) : isLoading || orgId === null ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : !tree || tree.roots.length === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">No groups yet for this organization.</p>
              <Button data-testid="create-root-group-empty" onClick={() => setCreateOpen(true)}>
                Create group
              </Button>
            </div>
          ) : (
            <div className="min-w-0">
              {rootNode ? (
                <PlateGroupTreeView
                  root={rootNode}
                  selectedId={null}
                  onSelect={(n) => router.push(`/inventory/plate-groups/${n.id}`)}
                  onRequestLoan={(n) => setLoanGroup(n)}
                />
              ) : null}
            </div>
          )}
        </TabsContent>

        <TabsContent value="insights" className="mt-4">
          <PlateInsightsPanel orgId={orgId ?? undefined} />
        </TabsContent>
      </Tabs>

      <PlateGroupDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        orgId={orgId ?? ""}
        parentGroupId={null}
        group={null}
      />
      <RequestLoanDialog
        open={loanGroup !== null}
        onOpenChange={(o) => {
          if (!o) setLoanGroup(null);
        }}
        orgId={orgId ?? undefined}
        initialGroupId={loanGroup?.id}
      />
    </div>
  );
}
