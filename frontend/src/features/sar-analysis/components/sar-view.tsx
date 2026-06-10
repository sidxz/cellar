"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { useCreateCollection } from "@/features/research-organization/hooks/use-collections";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useEffect, useState } from "react";
import { useRGroupDecomposition } from "../hooks/use-rgroup-decomposition";
import { readSarHandoff } from "../lib/sar-handoff";
import { RGroupCorePicker } from "./rgroup-core-picker";
import { RGroupTable } from "./rgroup-table";
import { SaveSelectionDialog } from "./save-selection-dialog";

export interface SarViewProps {
  molecules: Molecule[];
  collectionId?: string;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}

/**
 * R-group SAR view: a core picker, a decomposition table keyed off the chosen
 * core, and a "save selection → new collection" path that mirrors the cluster
 * view's create-then-bulk-add flow.
 */
export function SarView(props: SarViewProps) {
  const moleculeIds = props.molecules.map((m) => m.id);
  const decompose = useRGroupDecomposition();
  const createCollection = useCreateCollection();
  const [core, setCore] = useState<string | null>(() => readSarHandoff()?.coreSmiles ?? null);
  const [saveIds, setSaveIds] = useState<string[] | null>(null);

  // Re-run decomposition whenever the chosen core changes.
  // NOTE (v1 limitation): decomposes the currently-loaded `molecules` (the
  // visible page from the host). For collections larger than one page this
  // analyses the loaded subset; full-member decomposition is a follow-up.
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run only when the core or the source collection changes; `moleculeIds`/`decompose` would re-fire on every render (fresh array/mutation identity) — they're read from the latest closure, not tracked.
  useEffect(() => {
    if (!core) return;
    decompose.mutate({ moleculeIds, coreSmiles: core });
  }, [core, props.collectionId]);

  const result = decompose.data;

  return (
    <div className="flex flex-col gap-3">
      <RGroupCorePicker
        collectionId={props.collectionId}
        moleculeIds={moleculeIds}
        coreSmiles={core}
        onCoreChange={setCore}
        matchedCount={result?.assignments.length}
        totalCount={result ? result.assignments.length + result.unmatched_ids.length : undefined}
      />
      {decompose.isPending && <p className="text-xs text-muted-foreground">Decomposing…</p>}
      {result && (
        <RGroupTable
          decomposition={result}
          molecules={props.molecules}
          onSaveSelection={setSaveIds}
        />
      )}
      <SaveSelectionDialog
        open={saveIds != null}
        onOpenChange={(o) => !o && setSaveIds(null)}
        onSave={async ({ name, projectId, moleculeIds: selectedIds }) => {
          // Step 1: create the collection.
          const created = await new Promise<{ id: string }>((resolve, reject) =>
            createCollection.mutate(
              { name, project_id: projectId },
              { onSuccess: (c) => resolve(c as { id: string }), onError: (err) => reject(err) },
            ),
          );
          // Step 2: bulk-add the selected molecules to the new collection.
          if (selectedIds.length > 0) {
            await customInstance({
              url: `${API_V1}/collections/${created.id}/molecules`,
              method: "POST",
              data: { references: selectedIds.map((id) => ({ value: id, ref_type: "uuid" })) },
            });
          }
          setSaveIds(null);
        }}
        selectedMolecules={props.molecules.filter((m) => saveIds?.includes(m.id))}
        defaultName={`SAR selection from ${props.sourceLabel}`}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
    </div>
  );
}
