"use client";

import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { formatDate } from "@/shared/lib/format-date";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import {
  useDeletePlateGroup,
  usePlateGroup,
  usePlateGroupTree,
  useRemovePlatesFromGroup,
} from "../hooks/use-plate-groups";
import { LOAN_VARIANT, buildCustodyMap, useLoans } from "../hooks/use-plate-loans";
import { usePlates } from "../hooks/use-plates";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { AssignPlatesDialog } from "./assign-plates-dialog";
import { CommentFeed } from "./comment-feed";
import { MovePlateGroupDialog } from "./move-plate-group-dialog";
import { PlateGroupDialog } from "./plate-group-dialog";
import { formatInitial } from "./plate-group-tree-utils";
import { RequestLoanDialog } from "./request-loan-dialog";

type DialogState =
  | null
  | { kind: "create" }
  | { kind: "edit" }
  | { kind: "move" }
  | { kind: "assign" }
  | { kind: "delete" };

export interface PlateGroupPageProps {
  groupId: string;
}

export function PlateGroupPage({ groupId }: PlateGroupPageProps) {
  const router = useRouter();
  const query = usePlateGroup(groupId);
  const detail = query.data;
  const canEdit = useCanEdit();
  const { data: orgs } = useOrgs();
  const { data: locations } = useStorageLocations();
  const { data: plates } = usePlates({ group_id: groupId });
  const { data: openLoans } = useLoans({ status: "open" });
  const custodyByPlate = useMemo(() => buildCustodyMap(openLoans ?? []), [openLoans]);
  const orgNameById = useMemo(() => new Map((orgs ?? []).map((o) => [o.id, o.name])), [orgs]);

  const [dialog, setDialog] = useState<DialogState>(null);
  const [loanOpen, setLoanOpen] = useState(false);
  const closeDialog = (open: boolean) => {
    if (!open) setDialog(null);
  };

  const deleteGroup = useDeletePlateGroup();
  const removePlates = useRemovePlatesFromGroup();
  const orgTree = usePlateGroupTree(detail?.group.owner_org_id, {
    enabled: dialog?.kind === "move" && !!detail,
  });

  // The dialogs below take a full tree node; the detail response carries the
  // same fields plus the two summary counts, minus a `children` list they
  // don't need for a create/edit/move/assign/delete on THIS group.
  const node: PlateGroupNode | null = useMemo(() => {
    if (!detail) return null;
    return {
      ...detail.group,
      plate_count: detail.plate_count,
      plate_format: detail.plate_format,
      children: [],
    };
  }, [detail]);

  const orgName = useMemo(
    () => orgs?.find((o) => o.id === detail?.group.owner_org_id)?.name ?? "—",
    [orgs, detail],
  );
  const locationName = detail?.group.storage_location_id
    ? (locations?.find((l) => l.id === detail.group.storage_location_id)?.name ?? "…")
    : null;

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/plate-groups"
        backLabel="Back to Plate Groups"
        title={(d) => d.group.name}
        notFoundMessage="Plate group not found."
        breadcrumbTrail={(d) => [
          { label: "Plate Groups", href: "/inventory/plate-groups" },
          ...d.ancestors.map((a) => ({
            label: a.name,
            href: `/inventory/plate-groups/${a.id}`,
          })),
        ]}
        actions={(d) => (
          <>
            {d.subtree_plate_count > 0 ? (
              <Button size="sm" variant="outline" onClick={() => setLoanOpen(true)}>
                Request loan
              </Button>
            ) : null}
            <Button size="sm" variant="outline" onClick={() => setDialog({ kind: "assign" })}>
              Add plates
            </Button>
            <Button size="sm" onClick={() => setDialog({ kind: "create" })}>
              Add child
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDialog({ kind: "edit" })}>
              Edit
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDialog({ kind: "move" })}>
              Move
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setDialog({ kind: "delete" })}>
              Delete
            </Button>
          </>
        )}
      >
        {(d) => (
          <>
            <div className="-mt-3 flex flex-wrap items-center gap-2">
              {d.group.group_type ? <Badge variant="secondary">{d.group.group_type}</Badge> : null}
              {d.group.state ? <Badge variant="outline">{d.group.state}</Badge> : null}
              <span className="text-sm text-muted-foreground">{orgName}</span>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
              <div className="flex flex-col gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Details</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
                      {d.group.state ? (
                        <>
                          <dt className="text-muted-foreground">State</dt>
                          <dd>{d.group.state}</dd>
                        </>
                      ) : null}
                      {d.group.group_type ? (
                        <>
                          <dt className="text-muted-foreground">Type</dt>
                          <dd>{d.group.group_type}</dd>
                        </>
                      ) : null}
                      {d.plate_format ? (
                        <>
                          <dt className="text-muted-foreground">Format</dt>
                          <dd>{d.plate_format === "mixed" ? "mixed" : `${d.plate_format}-well`}</dd>
                        </>
                      ) : null}
                      {locationName ? (
                        <>
                          <dt className="text-muted-foreground">Location</dt>
                          <dd>{locationName}</dd>
                        </>
                      ) : null}
                      {d.group.scientist ? (
                        <>
                          <dt className="text-muted-foreground">Scientist</dt>
                          <dd>{d.group.scientist}</dd>
                        </>
                      ) : null}
                      {d.group.initial_volume_ul != null ||
                      d.group.initial_concentration_mm != null ? (
                        <>
                          <dt className="text-muted-foreground">Initial</dt>
                          <dd>
                            {formatInitial(
                              d.group.initial_volume_ul,
                              d.group.initial_concentration_mm,
                            )}
                          </dd>
                        </>
                      ) : null}
                      {d.group.compound_count != null ? (
                        <>
                          <dt className="text-muted-foreground">Compounds</dt>
                          <dd>{d.group.compound_count.toLocaleString("en-US")}</dd>
                        </>
                      ) : null}
                      <dt className="text-muted-foreground">Plates</dt>
                      <dd>
                        {d.plate_count} direct · {d.subtree_plate_count} in subtree
                      </dd>
                      <dt className="text-muted-foreground">Created</dt>
                      <dd>{formatDate(d.group.created_at)}</dd>
                      {d.group.description ? (
                        <>
                          <dt className="text-muted-foreground">Description</dt>
                          <dd>{d.group.description}</dd>
                        </>
                      ) : null}
                    </dl>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Child groups</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {d.children.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No child groups.</p>
                    ) : (
                      <ul className="divide-y rounded-md border">
                        {d.children.map((c) => (
                          <li key={c.id}>
                            <Link
                              href={`/inventory/plate-groups/${c.id}`}
                              className="flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-accent"
                            >
                              <span>{c.name}</span>
                              <span className="flex items-center gap-2">
                                {c.group_type ? (
                                  <Badge variant="secondary">{c.group_type}</Badge>
                                ) : null}
                                <Badge variant="outline">{c.plate_count ?? 0}</Badge>
                              </span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="flex flex-col gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Activity</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CommentFeed
                      scope={{ targetType: "plate_group", targetId: groupId }}
                      canWrite={canEdit}
                      emptyText="No activity yet — return notes and comments on this group appear here."
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Plates ({d.plate_count})</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {!plates?.length ? (
                      <p className="text-sm text-muted-foreground">No plates in this group.</p>
                    ) : (
                      <ul className="divide-y rounded-md border">
                        {plates.map((p) => {
                          const custody = custodyByPlate.get(p.id);
                          return (
                            <li
                              key={p.id}
                              className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm"
                            >
                              <Link
                                href={`/inventory/plates/${p.id}`}
                                className="font-mono text-primary hover:underline"
                              >
                                {p.barcode}
                              </Link>
                              <span className="text-muted-foreground">{p.plate_label}</span>
                              <StatusBadge status={p.status} />
                              {custody ? (
                                <StatusBadge
                                  status={custody.item.status}
                                  label={
                                    orgNameById.get(custody.loan.borrower_org_id) ?? "Unknown org"
                                  }
                                  variant={LOAN_VARIANT[custody.item.status]}
                                />
                              ) : null}
                              {canEdit ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="ml-auto"
                                  onClick={() => removePlates.mutate({ groupId, plateIds: [p.id] })}
                                  aria-label={`Remove ${p.barcode} from group`}
                                >
                                  Remove
                                </Button>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </>
        )}
      </DetailShell>

      {detail && node ? (
        <>
          <PlateGroupDialog
            open={dialog?.kind === "create" || dialog?.kind === "edit"}
            onOpenChange={closeDialog}
            orgId={detail.group.owner_org_id}
            parentGroupId={dialog?.kind === "create" ? groupId : null}
            group={dialog?.kind === "edit" ? node : null}
          />
          {orgTree.data ? (
            <MovePlateGroupDialog
              open={dialog?.kind === "move"}
              onOpenChange={closeDialog}
              group={node}
              tree={orgTree.data}
            />
          ) : null}
          <AssignPlatesDialog
            open={dialog?.kind === "assign"}
            onOpenChange={closeDialog}
            group={node}
          />
          <ConfirmDeleteDialog
            open={dialog?.kind === "delete"}
            onOpenChange={closeDialog}
            title={`Delete "${node.name}"?`}
            description="Plates in this group will be ungrouped, not deleted. A group that still has child groups can't be deleted — move or delete its children first."
            isPending={deleteGroup.isPending}
            onConfirm={() =>
              deleteGroup.mutate(
                { groupId },
                { onSuccess: () => router.push("/inventory/plate-groups") },
              )
            }
          />
          <RequestLoanDialog
            open={loanOpen}
            onOpenChange={setLoanOpen}
            orgId={detail.group.owner_org_id}
            initialGroupId={groupId}
          />
        </>
      ) : null}
    </>
  );
}
