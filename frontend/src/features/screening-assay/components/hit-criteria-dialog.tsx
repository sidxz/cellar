"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
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
import { useUpdateProtocol } from "../hooks/use-protocols";
import type { HitCriterion, ReadoutDefinition } from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OPERATOR_LABELS: Record<string, string> = {
  gt: ">",
  lt: "<",
  gte: ">=",
  lte: "<=",
  in: "in",
};

const COMPARISON_OPERATORS = ["gt", "lt", "gte", "lte"] as const;
const ALL_OPERATORS = ["gt", "lt", "gte", "lte", "in"] as const;

const MAX_RULES = 3;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface HitCriteriaDialogProps {
  protocolId: string;
  readoutDefinitions: ReadoutDefinition[];
  currentCriteria: HitCriterion[] | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Helper: build a default empty rule
// ---------------------------------------------------------------------------

function emptyRule(): HitCriterion {
  return { readout_name: "", operator: "gt", value: 0 };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function HitCriteriaDialog({
  protocolId,
  readoutDefinitions,
  currentCriteria,
  open,
  onOpenChange,
}: HitCriteriaDialogProps) {
  const updateProtocol = useUpdateProtocol(protocolId);
  const [rules, setRules] = useState<HitCriterion[]>(
    () => currentCriteria?.map((r) => ({ ...r })) ?? []
  );

  // Reset state when dialog opens
  const handleOpenChange = (next: boolean) => {
    if (next) {
      setRules(currentCriteria?.map((r) => ({ ...r })) ?? []);
    }
    onOpenChange(next);
  };

  // --- Rule manipulation ---------------------------------------------------

  const addRule = () => {
    if (rules.length >= MAX_RULES) return;
    setRules((prev) => [...prev, emptyRule()]);
  };

  const removeRule = (index: number) => {
    setRules((prev) => prev.filter((_, i) => i !== index));
  };

  const updateRule = (index: number, patch: Partial<HitCriterion>) => {
    setRules((prev) =>
      prev.map((r, i) => (i === index ? { ...r, ...patch } : r))
    );
  };

  const handleReadoutChange = (index: number, readoutName: string) => {
    const rule = rules[index];
    // When switching to "Curve Class", default to "in" operator with empty list
    if (readoutName === "Curve Class") {
      updateRule(index, {
        readout_name: readoutName,
        operator: "in",
        value: [],
      });
    } else if (rule.readout_name === "Curve Class") {
      // Switching away from Curve Class — reset to numeric comparison
      updateRule(index, {
        readout_name: readoutName,
        operator: "gt",
        value: 0,
      });
    } else {
      updateRule(index, { readout_name: readoutName });
    }
  };

  const handleOperatorChange = (
    index: number,
    operator: HitCriterion["operator"]
  ) => {
    if (operator === "in") {
      updateRule(index, { operator, value: [] });
    } else {
      const current = rules[index].value;
      updateRule(index, {
        operator,
        value: typeof current === "number" ? current : 0,
      });
    }
  };

  const handleValueChange = (index: number, raw: string) => {
    const rule = rules[index];
    if (rule.operator === "in") {
      // Comma-separated string values
      const parts = raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      updateRule(index, { value: parts });
    } else {
      const num = parseFloat(raw);
      updateRule(index, { value: isNaN(num) ? 0 : num });
    }
  };

  // --- Save ---------------------------------------------------------------

  const handleSave = () => {
    const payload = rules.length > 0 ? rules : null;
    updateProtocol.mutate(
      { recommended_hit_criteria: payload } as Record<string, unknown>,
      {
        onSuccess: () => onOpenChange(false),
      }
    );
  };

  // --- Derived state -------------------------------------------------------

  const readoutOptions = [
    ...readoutDefinitions.map((rd) => rd.name),
    "Curve Class",
  ];

  const isValid = rules.every(
    (r) =>
      r.readout_name !== "" &&
      (r.operator !== "in" ||
        (Array.isArray(r.value) && r.value.length > 0))
  );

  // --- Render --------------------------------------------------------------

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Hit Criteria</DialogTitle>
          <DialogDescription>
            Define up to {MAX_RULES} rules (combined with AND) to classify
            compounds as hits. These criteria are saved on the protocol and
            recommended to all users.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {rules.map((rule, index) => {
            const isCurveClass = rule.readout_name === "Curve Class";
            const operators = isCurveClass ? (["in"] as const) : ALL_OPERATORS;

            return (
              <div
                key={index}
                className="flex items-end gap-2 rounded-md border p-3"
              >
                {/* Readout selector */}
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">Readout</Label>
                  <Select
                    value={rule.readout_name}
                    onValueChange={(v) => handleReadoutChange(index, v)}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="Select readout" />
                    </SelectTrigger>
                    <SelectContent>
                      {readoutOptions.map((name) => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Operator selector */}
                <div className="w-20 space-y-1">
                  <Label className="text-xs">Op</Label>
                  <Select
                    value={rule.operator}
                    onValueChange={(v) =>
                      handleOperatorChange(
                        index,
                        v as HitCriterion["operator"]
                      )
                    }
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {operators.map((op) => (
                        <SelectItem key={op} value={op}>
                          {OPERATOR_LABELS[op]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Value input */}
                <div className="w-32 space-y-1">
                  <Label className="text-xs">Value</Label>
                  <Input
                    className="h-9"
                    type={rule.operator === "in" ? "text" : "number"}
                    placeholder={
                      rule.operator === "in" ? "full, partial" : "0"
                    }
                    value={
                      Array.isArray(rule.value)
                        ? rule.value.join(", ")
                        : rule.value
                    }
                    onChange={(e) => handleValueChange(index, e.target.value)}
                  />
                </div>

                {/* Remove button */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => removeRule(index)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            );
          })}

          {rules.length === 0 && (
            <p className="text-center text-sm text-muted-foreground">
              No rules defined. All compounds will be shown unfiltered.
            </p>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={addRule}
            disabled={rules.length >= MAX_RULES}
            className="w-full"
          >
            <Plus className="mr-2 h-4 w-4" />
            Add Rule
          </Button>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateProtocol.isPending || (!isValid && rules.length > 0)}
          >
            {updateProtocol.isPending ? "Saving..." : "Save Criteria"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
