"use client";

import { type SaltEntry, useSaltCatalog } from "@/features/workspace-config/hooks/use-salt-catalog";
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
import { useCallback, useEffect, useMemo, useState } from "react";
import { useCreateBatch } from "../hooks/use-batches";
import { BATCH_SOURCE_LABELS } from "../types";
import { MoleculeSelector } from "./molecule-selector";

const NONE_VALUE = "__none__";

interface CreateBatchDialogProps {
  moleculeId?: string;
  moleculeMw?: number;
  detectedSalt?: {
    salt_smiles: string;
    salt_fragment_mw: number;
    stoichiometry: number;
  } | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateBatchDialog({
  moleculeId,
  moleculeMw,
  detectedSalt,
  open,
  onOpenChange,
}: CreateBatchDialogProps) {
  const createMutation = useCreateBatch();
  const { data: saltEntries } = useSaltCatalog(true);

  const [selectedMoleculeId, setSelectedMoleculeId] = useState<string | null>(moleculeId ?? null);
  const [source, setSource] = useState<string>("synthesized");
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");
  const [saltEntryId, setSaltEntryId] = useState<string>(NONE_VALUE);
  const [stoichiometry, setStoichiometry] = useState<number>(1);
  const [purity, setPurity] = useState("");
  const [appearance, setAppearance] = useState("");

  const selectedSalt = useMemo<SaltEntry | undefined>(
    () => (saltEntryId !== NONE_VALUE ? saltEntries?.find((e) => e.id === saltEntryId) : undefined),
    [saltEntryId, saltEntries],
  );

  const formulaWeight = useMemo<number | null>(() => {
    if (!selectedSalt || moleculeMw == null) return null;
    return moleculeMw + selectedSalt.molecular_weight * stoichiometry;
  }, [selectedSalt, moleculeMw, stoichiometry]);

  // Auto-fill from detected salt
  useEffect(() => {
    if (!detectedSalt || !saltEntries?.length) return;
    const match = saltEntries.find((e) => e.smiles === detectedSalt.salt_smiles);
    if (match) {
      setSaltEntryId(match.id);
      setStoichiometry(detectedSalt.stoichiometry);
    }
  }, [detectedSalt, saltEntries]);

  const resetForm = useCallback(() => {
    setSource("synthesized");
    setAmountValue("");
    setAmountUnit("mg");
    setSaltEntryId(NONE_VALUE);
    setStoichiometry(1);
    setPurity("");
    setAppearance("");
    if (!moleculeId) setSelectedMoleculeId(null);
  }, [moleculeId]);

  const resolvedMoleculeId = selectedMoleculeId ?? moleculeId;

  const handleSubmit = () => {
    if (!resolvedMoleculeId) return;
    createMutation.mutate(
      {
        molecule_id: resolvedMoleculeId,
        source,
        amount_value: Number.parseFloat(amountValue),
        amount_unit: amountUnit,
        salt_entry_id: selectedSalt ? selectedSalt.id : null,
        salt_name: selectedSalt ? selectedSalt.name : null,
        salt_smiles: selectedSalt ? selectedSalt.smiles : null,
        salt_stoichiometry: selectedSalt ? stoichiometry : undefined,
        formula_weight: formulaWeight,
        purity: purity ? Number.parseFloat(purity) : null,
        appearance: appearance || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          resetForm();
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Batch</DialogTitle>
          <DialogDescription>Register a new batch for this compound.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {!moleculeId && (
            <div className="grid gap-2">
              <Label>Compound *</Label>
              <MoleculeSelector selectedId={selectedMoleculeId} onSelect={setSelectedMoleculeId} />
            </div>
          )}

          <div className="grid gap-2">
            <Label>Source</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(BATCH_SOURCE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Amount</Label>
              <Input
                type="number"
                placeholder="100"
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Unit</Label>
              <Select value={amountUnit} onValueChange={setAmountUnit}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mg">mg</SelectItem>
                  <SelectItem value="g">g</SelectItem>
                  <SelectItem value="kg">kg</SelectItem>
                  <SelectItem value="mL">mL</SelectItem>
                  <SelectItem value="L">L</SelectItem>
                  <SelectItem value="umol">umol</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Purity (%)</Label>
            <Input
              type="number"
              placeholder="99.5"
              value={purity}
              onChange={(e) => setPurity(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Salt Form</Label>
            <Select value={saltEntryId} onValueChange={setSaltEntryId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE_VALUE}>None / Free base</SelectItem>
                {saltEntries?.map((entry) => (
                  <SelectItem key={entry.id} value={entry.id}>
                    {entry.code} &mdash; {entry.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedSalt && (
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label>Stoichiometry</Label>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={stoichiometry}
                  onChange={(e) =>
                    setStoichiometry(Math.max(1, Number.parseInt(e.target.value) || 1))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label>Formula Weight</Label>
                <Input
                  readOnly
                  value={formulaWeight != null ? formulaWeight.toFixed(2) : "\u2014"}
                  className="bg-muted"
                />
              </div>
            </div>
          )}

          <div className="grid gap-2">
            <Label>Appearance</Label>
            <Input
              placeholder="e.g., white powder"
              value={appearance}
              onChange={(e) => setAppearance(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!resolvedMoleculeId || !amountValue || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Batch"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
