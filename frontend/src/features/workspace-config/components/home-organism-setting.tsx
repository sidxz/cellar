"use client";

import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { useState } from "react";
import { usePreviewNamingChange, useSetHomeOrganism } from "../hooks/use-naming-changes";
import type { ProtocolNamingSettings } from "../types";
import { NamingChangePreview } from "./naming-change-preview";

type Home = NonNullable<ProtocolNamingSettings["home_organism"]>;

/** The organism a workspace studies: its targets are named without it. Changing it relabels
 *  protocols, so it previews the renames and saves through its own setting. */
export function HomeOrganismSetting({ current }: { current: Home | null }) {
  const [picked, setPicked] = useState<OntologyTerm[]>(
    current ? [{ ...current, uri: null } as OntologyTerm] : [],
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const preview = usePreviewNamingChange();
  const setHome = useSetHomeOrganism();

  const term = picked[0]
    ? {
        term_id: picked[0].term_id,
        label: picked[0].label,
        ontology_source: picked[0].ontology_source,
      }
    : null;
  const unchanged = (term?.term_id ?? null) === (current?.term_id ?? null);

  return (
    <div className="grid gap-2">
      <Label>Home organism</Label>
      <OntologySearchInput
        ontologySources={["NCBITAXON"]}
        value={picked}
        onChange={(terms) => setPicked(terms.slice(-1))}
        placeholder="e.g. Mycobacterium tuberculosis"
      />
      <p className="text-xs text-muted-foreground">
        Targets from this organism are named without it (PptT inhibition, not M. tuberculosis PptT
        inhibition).
      </p>
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={unchanged || preview.isPending}
          onClick={() =>
            preview.mutate(
              { kind: "home_organism", term },
              { onSuccess: () => setConfirmOpen(true) },
            )
          }
        >
          Change home organism
        </Button>
      </div>
      <NamingChangePreview
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        preview={preview.data}
        isLoading={preview.isPending}
        onApply={async () => {
          await setHome.mutateAsync({ term });
          setConfirmOpen(false);
        }}
        isApplying={setHome.isPending}
      />
    </div>
  );
}
