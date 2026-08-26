"use client";

import { RequestLoanDialog } from "@/features/inventory/components/request-loan-dialog";
import type { CollectionPlateGroup } from "@/features/inventory/hooks/use-plate-groups";
import { useCollectionPlateGroups } from "@/features/inventory/hooks/use-plate-groups";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import Link from "next/link";
import { useState } from "react";

/** Plate groups (any level) that physically realize this collection (S16 §7). */
export function CollectionPlateGroupsCard({ collectionId }: { collectionId: string }) {
  const { data: groups } = useCollectionPlateGroups(collectionId);
  const canEdit = useCanEdit();
  const [loanTarget, setLoanTarget] = useState<CollectionPlateGroup | null>(null);

  return (
    <>
      <Card data-testid="collection-plate-groups">
        <CardHeader>
          <CardTitle className="text-base">Physical plates</CardTitle>
        </CardHeader>
        <CardContent>
          {!groups?.length ? (
            <p className="text-sm text-muted-foreground">
              No plate groups realize this collection yet — link one from a group's Edit dialog.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {groups.map((g) => (
                <li
                  key={g.group_id}
                  className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm"
                >
                  <Link
                    href={`/inventory/plate-groups/${g.group_id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {g.path}
                  </Link>
                  {g.group_type ? <Badge variant="secondary">{g.group_type}</Badge> : null}
                  <span className="text-muted-foreground">
                    {g.subtree_plate_count} plate{g.subtree_plate_count === 1 ? "" : "s"}
                  </span>
                  {g.on_loan_count > 0 ? (
                    <span className="text-warning">{g.on_loan_count} on loan</span>
                  ) : null}
                  {g.overdue_count > 0 ? (
                    <span className="text-destructive">{g.overdue_count} overdue</span>
                  ) : null}
                  {canEdit && g.subtree_plate_count > 0 ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ml-auto"
                      onClick={() => setLoanTarget(g)}
                    >
                      Request loan
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <RequestLoanDialog
        open={loanTarget !== null}
        onOpenChange={(open) => {
          if (!open) setLoanTarget(null);
        }}
        orgId={loanTarget?.owner_org_id}
        initialGroupId={loanTarget?.group_id}
      />
    </>
  );
}
