"use client";

import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { useState } from "react";
import { usePreviewNamingChange, useSetHomeOrganism } from "../hooks/use-naming-changes";
import type { ProtocolNamingSettings } from "../types";
import { NamingChangePreview } from "./naming-change-preview";

type Home = { term_id: string; label: string; ontology_source: string };

/** The organisms in protocol_naming (an opaque dict). Before the list form, a single
 *  `home_organism` was stored; it reads as a one-item list. */
export function homeOrganismsFrom(
  naming: Pick<ProtocolNamingSettings, "home_organisms" | "home_organism"> | undefined,
): Home[] {
  if (naming?.home_organisms) return naming.home_organisms;
  return naming?.home_organism ? [naming.home_organism] : [];
}

const toTerm = (t: OntologyTerm): Home => ({
  term_id: t.term_id,
  label: t.label,
  ontology_source: t.ontology_source,
});

/** The organisms a workspace studies: their targets are named without the organism. Changing
 *  them relabels protocols, so it previews the renames and saves through its own setting. */
export function HomeOrganismSetting({ current }: { current: Home[] }) {
  const [picked, setPicked] = useState<OntologyTerm[]>(
    current.map((c) => ({ ...c, uri: null }) as OntologyTerm),
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const preview = usePreviewNamingChange();
  const setHome = useSetHomeOrganism();

  const terms = picked.map(toTerm);
  const unchanged =
    terms.length === current.length &&
    terms.every((t) => current.some((c) => c.term_id === t.term_id));

  return (
    <div id="home-organisms" className="grid scroll-mt-20 gap-2">
      <Label>Home organisms</Label>
      <OntologySearchInput
        ontologySources={["NCBITAXON"]}
        slot="organism"
        value={picked}
        onChange={setPicked}
        placeholder="e.g. Mycobacterium tuberculosis"
      />
      <p className="text-xs text-muted-foreground">
        Generated protocol names omit the organism for targets from the organisms selected here. For
        example, “M. tuberculosis PptT inhibition” becomes “PptT inhibition”.
      </p>
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={unchanged || preview.isPending}
          onClick={() =>
            preview.mutate(
              { kind: "home_organism", terms },
              { onSuccess: () => setConfirmOpen(true) },
            )
          }
        >
          Change home organisms
        </Button>
      </div>
      <NamingChangePreview
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        preview={preview.data}
        isLoading={preview.isPending}
        onApply={async () => {
          await setHome.mutateAsync({ terms });
          setConfirmOpen(false);
        }}
        isApplying={setHome.isPending}
      />
    </div>
  );
}
