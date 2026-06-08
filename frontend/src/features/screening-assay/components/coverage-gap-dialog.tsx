"use client";

import { useMoleculesByIds } from "@/features/chemical-registration";
import type { Molecule } from "@/features/chemical-registration/types";
import { MoleculeCard } from "@/features/research-organization/components/results/molecule-card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

/** Page size for the gap fetch — matches the v1 endpoint's max window. */
const GAP_LIMIT = 200;

export interface CoverageGapDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Resource path of the coverage subject, e.g. `/runs/{id}/collections/{cid}`
   *  or `/protocols/{id}/collections/{cid}`. The dialog fetches `{path}/gap`. */
  gapBasePath: string;
  collectionName: string;
}

/**
 * Lists the molecules in a collection that the run/protocol has NOT screened
 * yet (the "coverage gap"). Fetches the unscreened molecule ids from the gap
 * endpoint, resolves them to full molecules via the existing bulk-by-ids hook,
 * and renders each through the shared `MoleculeCard` so the cards match the
 * collection-detail surface. Read-only — selection is a no-op.
 */
export function CoverageGapDialog({
  open,
  onOpenChange,
  gapBasePath,
  collectionName,
}: CoverageGapDialogProps) {
  const router = useRouter();

  const gapQuery = useQuery({
    queryKey: ["coverage-gap", gapBasePath],
    enabled: open,
    queryFn: () =>
      customInstance<string[]>({
        url: `${API_V1}${gapBasePath}/gap`,
        method: "GET",
        params: { offset: "0", limit: String(GAP_LIMIT) },
      }),
  });

  const gapIds = gapQuery.data ?? [];
  const { data: moleculesPage } = useMoleculesByIds(gapIds);
  const molecules = moleculesPage?.items ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-4xl flex-col">
        <DialogHeader>
          <DialogTitle>Unscreened in {collectionName}</DialogTitle>
          <DialogDescription>
            {gapQuery.isLoading
              ? "Loading unscreened molecules…"
              : `${gapIds.length.toLocaleString("en-US")} molecule${
                  gapIds.length === 1 ? "" : "s"
                } not yet screened${gapIds.length >= GAP_LIMIT ? ` (showing first ${GAP_LIMIT})` : ""}.`}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="-mx-2 flex-1 px-2">
          {gapQuery.isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
          ) : gapIds.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Every molecule in this collection has been screened.
            </p>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3 py-1">
              {molecules.map((m) => (
                <MoleculeCard
                  key={m.id}
                  molecule={m as unknown as Molecule}
                  selected={false}
                  onSelectChange={() => {}}
                  onOpen={(id) => router.push(`/compounds/${id}`)}
                />
              ))}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
