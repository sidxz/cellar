"use client";

import type { ReadoutNormalization } from "@/features/screening-assay/types";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Label } from "@/shared/components/ui/label";

const FORMULAS: Array<{
  value: Exclude<ReadoutNormalization, "none">;
  label: string;
  description: string;
}> = [
  {
    value: "percent_inhibition",
    label: "% Inhibition",
    description: "Normalized against positive and negative controls",
  },
  {
    value: "percent_activation",
    label: "% Activation",
    description: "Normalized against positive and negative controls",
  },
  {
    value: "percent_control",
    label: "% Control",
    description: "Normalized against positive control mean",
  },
  {
    value: "z_score",
    label: "Z-Score",
    description: "Standard deviations from positive control mean",
  },
];

export interface NormalizationCheckboxGroupProps {
  /** Currently selected formulas. Empty array means no normalization. */
  value: ReadoutNormalization[];
  onChange?: (next: ReadoutNormalization[]) => void;
  disabled?: boolean;
}

/**
 * Multi-checkbox normalization picker. A single readout def can emit
 * multiple normalized columns at once (raw + %inh + z-score), so this
 * component is multi-select. The empty array represents the legacy
 * "none" option.
 */
export function NormalizationCheckboxGroup({
  value,
  onChange,
  disabled = false,
}: NormalizationCheckboxGroupProps) {
  const set = new Set(value);

  const toggle = (formula: Exclude<ReadoutNormalization, "none">) => {
    if (!onChange) return;
    const next = new Set(set);
    if (next.has(formula)) {
      next.delete(formula);
    } else {
      next.add(formula);
    }
    onChange(Array.from(next));
  };

  return (
    <div className="space-y-1.5">
      {FORMULAS.map((f) => {
        const checked = set.has(f.value);
        return (
          <div key={f.value} className="flex items-start gap-2 py-0.5">
            <Checkbox
              id={`norm-${f.value}`}
              checked={checked}
              onCheckedChange={() => toggle(f.value)}
              disabled={disabled}
              className="mt-0.5"
            />
            <div className="grid gap-0.5 leading-tight">
              <Label
                htmlFor={`norm-${f.value}`}
                className={disabled ? "cursor-not-allowed text-foreground" : "cursor-pointer"}
              >
                {f.label}
              </Label>
              <p className="text-xs text-muted-foreground">{f.description}</p>
            </div>
          </div>
        );
      })}
      {value.length === 0 && (
        <p className="text-xs italic text-muted-foreground">
          No normalization selected — values are stored as raw measurements.
        </p>
      )}
    </div>
  );
}
