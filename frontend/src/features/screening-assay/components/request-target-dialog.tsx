"use client";

import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useRequestTarget } from "../hooks/use-targets";
import { TARGET_TYPE_LABELS, type Target, type TargetType } from "../types";

/** Types ProtCellar can create from one protein or none. Complexes, families and
 *  interactions need several proteins and are made in ProtCellar itself. */
const REQUESTABLE: TargetType[] = [
  "single_protein",
  "domain",
  "organism",
  "cell_line",
  "tissue",
  "nucleic_acid",
  "unknown",
];
const NEEDS_PROTEIN = new Set<TargetType>(["single_protein", "domain"]);

/** The server's own sentence: `message` is the friendly text, `detail` the raw cause. */
function errorText(error: Error): string {
  const body = error instanceof ApiError ? (error.body as { message?: unknown } | null) : null;
  return typeof body?.message === "string" ? body.message : error.message;
}

interface RequestTargetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (target: Target) => void;
}

/** Create a missing target in ProtCellar from a target picker. Explicit submit; the
 *  new target comes back mirrored and is handed to the picker to select. */
export function RequestTargetDialog({ open, onOpenChange, onCreated }: RequestTargetDialogProps) {
  const [name, setName] = useState("");
  const [targetType, setTargetType] = useState<TargetType>("single_protein");
  const [protein, setProtein] = useState("");
  const [organism, setOrganism] = useState<OntologyTerm[]>([]);
  const [chemblId, setChemblId] = useState("");
  const request = useRequestTarget();

  const needsProtein = NEEDS_PROTEIN.has(targetType);
  const picked = organism[0];
  const canSubmit =
    name.trim() !== "" &&
    picked !== undefined &&
    (!needsProtein || protein.trim() !== "") &&
    !request.isPending;

  const submit = () => {
    if (!canSubmit) return;
    request.mutate(
      {
        name: name.trim(),
        target_type: targetType,
        organism_term_id: picked.term_id,
        organism_label: picked.label,
        chembl_id: chemblId.trim() || null,
        protein_identifier: needsProtein ? protein.trim() : null,
      },
      { onSuccess: (target) => onCreated(target) },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && request.isPending) return;
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Request a new target</DialogTitle>
          <DialogDescription>
            The target is created in ProtCellar under your name and is ready to use here at once.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="request-target-name">Name</Label>
            <Input
              id="request-target-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. hERG"
            />
            <p className="text-muted-foreground text-xs">
              Use the usual short name, such as hERG or InhA.
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="request-target-type">Target type</Label>
            <Select value={targetType} onValueChange={(v) => setTargetType(v as TargetType)}>
              <SelectTrigger id="request-target-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REQUESTABLE.map((t) => (
                  <SelectItem key={t} value={t}>
                    {TARGET_TYPE_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {needsProtein && (
            <div className="grid gap-2">
              <Label htmlFor="request-target-protein">UniProt accession or entry name</Label>
              <Input
                id="request-target-protein"
                value={protein}
                onChange={(e) => setProtein(e.target.value)}
                placeholder="e.g. Q12809 or KCNH2_HUMAN"
              />
              <p className="text-muted-foreground text-xs">
                The protein must already be in ProtCellar.
              </p>
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="request-target-organism">Organism</Label>
            <OntologySearchInput
              id="request-target-organism"
              ontologySources={["NCBITAXON"]}
              slot="organism"
              value={organism}
              onChange={(terms) => setOrganism(terms.slice(-1))}
              placeholder="e.g. human, Mtb"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="request-target-chembl">ChEMBL ID (optional)</Label>
            <Input
              id="request-target-chembl"
              value={chemblId}
              onChange={(e) => setChemblId(e.target.value)}
              placeholder="e.g. CHEMBL240"
            />
          </div>

          {request.error && (
            <p role="alert" className="text-destructive text-sm">
              {errorText(request.error)}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={request.isPending}
          >
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {request.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Request target
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
