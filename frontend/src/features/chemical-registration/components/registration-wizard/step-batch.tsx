"use client";

import { Package, CheckCircle2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useSaltCatalog } from "@/features/workspace-config/hooks/use-salt-catalog";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import type { WizardBatchInput } from "../../hooks/use-registration-wizard";

// ─── Constants ───────────────────────────────────────────────────────────────

const SOURCE_OPTIONS = [
  { value: "synthesized", label: "Synthesized" },
  { value: "purchased", label: "Purchased" },
  { value: "donated", label: "Donated" },
] as const;

const AMOUNT_UNITS = ["mg", "g", "μg", "mL"] as const;

// ─── StepBatch ───────────────────────────────────────────────────────────────

export function StepBatch() {
  const singleResult = useRegistrationWizard((s) => s.singleResult);
  const batchInput = useRegistrationWizard((s) => s.batchInput);
  const setBatchInput = useRegistrationWizard((s) => s.setBatchInput);
  const nextStep = useRegistrationWizard((s) => s.nextStep);

  const saltCatalog = useSaltCatalog(true);
  const salts = saltCatalog.data ?? [];

  // ─── If registration already created a batch, show confirmation ──────────
  if (singleResult?.batch) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
            Batch Created
          </CardTitle>
          <CardDescription>
            A batch was automatically created during registration.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md bg-muted/50 p-4">
            <p className="text-sm font-medium">
              Batch{" "}
              <span className="font-semibold text-foreground">
                {singleResult.batch.batch_number}
              </span>{" "}
              was created for{" "}
              <span className="font-semibold text-foreground">
                {singleResult.molecule.registration_number}
              </span>
              .
            </p>
          </div>
          <div className="flex justify-end border-t pt-4">
            <Button onClick={nextStep}>Continue to Summary</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // ─── No batch from registration — show optional form ────────────────────

  const current: WizardBatchInput = batchInput ?? {
    source: "synthesized",
    amountValue: null,
    amountUnit: "mg",
    purity: null,
    saltEntryId: null,
    saltStoichiometry: 1,
    appearance: null,
  };

  function patch(update: Partial<WizardBatchInput>) {
    setBatchInput({ ...current, ...update });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Package className="h-5 w-5 text-muted-foreground" />
          Create Batch (Optional)
        </CardTitle>
        <CardDescription>
          A batch will be auto-created with defaults if you skip this step.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        {/* Source */}
        <div className="space-y-1.5">
          <Label htmlFor="batch-source">Source</Label>
          <Select
            value={current.source}
            onValueChange={(v) => patch({ source: v })}
          >
            <SelectTrigger id="batch-source">
              <SelectValue placeholder="Select source" />
            </SelectTrigger>
            <SelectContent>
              {SOURCE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Amount */}
        <div className="space-y-1.5">
          <Label>Amount</Label>
          <div className="flex gap-2">
            <Input
              type="number"
              min={0}
              step="any"
              placeholder="e.g. 100"
              value={current.amountValue ?? ""}
              onChange={(e) =>
                patch({
                  amountValue: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="flex-1"
            />
            <Select
              value={current.amountUnit}
              onValueChange={(v) => patch({ amountUnit: v })}
            >
              <SelectTrigger className="w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AMOUNT_UNITS.map((u) => (
                  <SelectItem key={u} value={u}>
                    {u}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Purity */}
        <div className="space-y-1.5">
          <Label htmlFor="batch-purity">Purity (%)</Label>
          <Input
            id="batch-purity"
            type="number"
            min={0}
            max={100}
            step="any"
            placeholder="e.g. 99.5"
            value={current.purity ?? ""}
            onChange={(e) =>
              patch({ purity: e.target.value ? Number(e.target.value) : null })
            }
          />
        </div>

        {/* Appearance */}
        <div className="space-y-1.5">
          <Label htmlFor="batch-appearance">Appearance</Label>
          <Input
            id="batch-appearance"
            type="text"
            placeholder="e.g. White crystalline powder"
            value={current.appearance ?? ""}
            onChange={(e) =>
              patch({ appearance: e.target.value || null })
            }
          />
        </div>

        {/* Salt form — only shown if salt catalog has entries */}
        {salts.length > 0 && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="batch-salt">Salt Form</Label>
              <Select
                value={current.saltEntryId ?? "__none__"}
                onValueChange={(v) =>
                  patch({ saltEntryId: v === "__none__" ? null : v })
                }
              >
                <SelectTrigger id="batch-salt">
                  <SelectValue placeholder="None (free base)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None (free base)</SelectItem>
                  {salts.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name} ({s.code})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {current.saltEntryId && (
              <div className="space-y-1.5">
                <Label htmlFor="batch-salt-stoich">Salt Stoichiometry</Label>
                <Input
                  id="batch-salt-stoich"
                  type="number"
                  min={1}
                  step={1}
                  value={current.saltStoichiometry}
                  onChange={(e) =>
                    patch({
                      saltStoichiometry: e.target.value
                        ? Number(e.target.value)
                        : 1,
                    })
                  }
                  className="w-32"
                />
              </div>
            )}
          </>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 border-t pt-4">
          <Button onClick={nextStep}>Skip &amp; Auto-Create</Button>
          <Button variant="outline" onClick={nextStep}>
            Save Batch Info &amp; Continue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
