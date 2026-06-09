"use client";

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
import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useUpdateProtocol } from "../hooks/use-protocols";
import { useResetRunHitCriteria, useSetRunHitCriteria } from "../hooks/use-runs";
import { buildHitCriterionOptions, optionIdForRule } from "../lib/hit-criteria-options";
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

const ALL_OPERATORS = ["gt", "lt", "gte", "lte", "in"] as const;

const MAX_RULES = 3;

function emptyRule(): HitCriterion {
  return { readout_name: "", operator: "gt", value: 0, intercept_key: null };
}

// ---------------------------------------------------------------------------
// Shared rule-editing state
//
// One hook owns the draft rules + their stable row keys (so focus and
// uncommitted text stay attached to the right row across add / remove) plus
// every mutation handler and the validity check. Both the protocol-scoped and
// run-scoped dialogs build on this — the only difference between them is where
// the saved rules are persisted.
// ---------------------------------------------------------------------------

interface HitCriteriaRulesState {
  rules: HitCriterion[];
  rowKeys: string[];
  options: ReturnType<typeof buildHitCriterionOptions>;
  isValid: boolean;
  reset: (initial: HitCriterion[] | null) => void;
  addRule: () => void;
  removeRule: (index: number) => void;
  handleOptionChange: (index: number, optionId: string) => void;
  handleOperatorChange: (index: number, operator: HitCriterion["operator"]) => void;
  handleValueChange: (index: number, raw: string) => void;
}

function useHitCriteriaRules(
  readoutDefinitions: ReadoutDefinition[],
  initial: HitCriterion[] | null,
): HitCriteriaRulesState {
  const [rules, setRules] = useState<HitCriterion[]>(() => initial?.map((r) => ({ ...r })) ?? []);
  // `HitCriterion` is the backend payload, so the React key lives outside it.
  const [rowKeys, setRowKeys] = useState<string[]>(() =>
    (initial ?? []).map(() => crypto.randomUUID()),
  );

  const options = useMemo(() => buildHitCriterionOptions(readoutDefinitions), [readoutDefinitions]);

  const reset = (next: HitCriterion[] | null) => {
    setRules(next?.map((r) => ({ ...r })) ?? []);
    setRowKeys((next ?? []).map(() => crypto.randomUUID()));
  };

  const addRule = () => {
    if (rules.length >= MAX_RULES) return;
    setRules((prev) => [...prev, emptyRule()]);
    setRowKeys((prev) => [...prev, crypto.randomUUID()]);
  };

  const removeRule = (index: number) => {
    setRules((prev) => prev.filter((_, i) => i !== index));
    setRowKeys((prev) => prev.filter((_, i) => i !== index));
  };

  const updateRule = (index: number, patch: Partial<HitCriterion>) => {
    setRules((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const handleOptionChange = (index: number, optionId: string) => {
    const opt = options.find((o) => o.id === optionId);
    if (!opt) return;
    const rule = rules[index];
    if (opt.readout_name === "Curve Class") {
      updateRule(index, {
        readout_name: "Curve Class",
        operator: "in",
        value: [],
        intercept_key: null,
      });
    } else if (rule.readout_name === "Curve Class") {
      // Switching away from Curve Class — reset to a numeric comparison
      updateRule(index, {
        readout_name: opt.readout_name,
        intercept_key: opt.intercept_key,
        operator: "gt",
        value: 0,
      });
    } else {
      updateRule(index, {
        readout_name: opt.readout_name,
        intercept_key: opt.intercept_key,
      });
    }
  };

  const handleOperatorChange = (index: number, operator: HitCriterion["operator"]) => {
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
      const parts = raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      updateRule(index, { value: parts });
    } else {
      const num = Number.parseFloat(raw);
      updateRule(index, { value: Number.isNaN(num) ? 0 : num });
    }
  };

  const isValid = rules.every(
    (r) =>
      r.readout_name !== "" &&
      (r.operator !== "in" || (Array.isArray(r.value) && r.value.length > 0)),
  );

  return {
    rules,
    rowKeys,
    options,
    isValid,
    reset,
    addRule,
    removeRule,
    handleOptionChange,
    handleOperatorChange,
    handleValueChange,
  };
}

// ---------------------------------------------------------------------------
// Shared presentational editor — the rule rows + add button
// ---------------------------------------------------------------------------

function HitCriteriaRulesEditor({
  state,
  readoutDefinitions,
}: {
  state: HitCriteriaRulesState;
  readoutDefinitions: ReadoutDefinition[];
}) {
  const { rules, rowKeys, options } = state;
  return (
    <div className="space-y-4 py-2">
      {rules.map((rule, index) => {
        const isCurveClass = rule.readout_name === "Curve Class";
        const operators = isCurveClass ? (["in"] as const) : ALL_OPERATORS;
        return (
          <div key={rowKeys[index]} className="flex items-end gap-2 rounded-md border p-3">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Readout</Label>
              <Select
                value={rule.readout_name === "" ? "" : optionIdForRule(rule, readoutDefinitions)}
                onValueChange={(v) => state.handleOptionChange(index, v)}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select readout" />
                </SelectTrigger>
                <SelectContent>
                  {options.map((opt) => (
                    <SelectItem key={opt.id} value={opt.id}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="w-20 space-y-1">
              <Label className="text-xs">Op</Label>
              <Select
                value={rule.operator}
                onValueChange={(v) =>
                  state.handleOperatorChange(index, v as HitCriterion["operator"])
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

            <div className="w-32 space-y-1">
              <Label className="text-xs">Value</Label>
              <Input
                className="h-9"
                type={rule.operator === "in" ? "text" : "number"}
                placeholder={rule.operator === "in" ? "full, partial" : "0"}
                value={Array.isArray(rule.value) ? rule.value.join(", ") : rule.value}
                onChange={(e) => state.handleValueChange(index, e.target.value)}
              />
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9 shrink-0 text-muted-foreground hover:text-destructive"
              onClick={() => state.removeRule(index)}
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
        onClick={state.addRule}
        disabled={rules.length >= MAX_RULES}
        className="w-full"
      >
        <Plus className="mr-2 h-4 w-4" />
        Add Rule
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Protocol-scoped dialog — edits the protocol's *recommended* criteria (the SOP
// suggestion). Used on protocol surfaces (e.g. the activity tab). Empty rules
// clear the recommendation (None).
// ---------------------------------------------------------------------------

interface HitCriteriaDialogProps {
  protocolId: string;
  readoutDefinitions: ReadoutDefinition[];
  currentCriteria: HitCriterion[] | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function HitCriteriaDialog({
  protocolId,
  readoutDefinitions,
  currentCriteria,
  open,
  onOpenChange,
}: HitCriteriaDialogProps) {
  const updateProtocol = useUpdateProtocol(protocolId);
  const state = useHitCriteriaRules(readoutDefinitions, currentCriteria);

  const handleOpenChange = (next: boolean) => {
    if (next) state.reset(currentCriteria);
    onOpenChange(next);
  };

  const handleSave = () => {
    const payload = state.rules.length > 0 ? state.rules : null;
    updateProtocol.mutate({ recommended_hit_criteria: payload } as Record<string, unknown>, {
      onSuccess: () => onOpenChange(false),
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Recommended Hit Criteria</DialogTitle>
          <DialogDescription>
            Define up to {MAX_RULES} rules (combined with AND) to classify compounds as hits. These
            criteria are saved on the protocol and recommended to all runs — each run still chooses
            whether to apply them.
          </DialogDescription>
        </DialogHeader>

        <HitCriteriaRulesEditor state={state} readoutDefinitions={readoutDefinitions} />

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateProtocol.isPending || (!state.isValid && state.rules.length > 0)}
          >
            {updateProtocol.isPending ? "Saving..." : "Save Criteria"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Run-scoped dialog — records *this run's* hit criteria (an attributable
// analytical decision). When customizing from an unset run, the editor is
// seeded with the protocol recommendation as a starting point. Saving with zero
// rules is a valid, recorded "show all" decision (not a clear) — to revert to
// unset, use "Reset to recommended" on the filter bar.
// ---------------------------------------------------------------------------

interface RunHitCriteriaDialogProps {
  runId: string;
  readoutDefinitions: ReadoutDefinition[];
  /** The run's own criteria (null = unset). */
  currentCriteria: HitCriterion[] | null;
  /** The protocol's recommended criteria — seeds the editor when customizing
   *  from an unset run. */
  recommendation: HitCriterion[] | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RunHitCriteriaDialog({
  runId,
  readoutDefinitions,
  currentCriteria,
  recommendation,
  open,
  onOpenChange,
}: RunHitCriteriaDialogProps) {
  const setHitCriteria = useSetRunHitCriteria();
  const resetHitCriteria = useResetRunHitCriteria();
  const seed = currentCriteria ?? recommendation ?? [];
  const state = useHitCriteriaRules(readoutDefinitions, seed);

  const handleOpenChange = (next: boolean) => {
    if (next) state.reset(currentCriteria ?? recommendation ?? []);
    onOpenChange(next);
  };

  const handleSave = () => {
    // Empty rules → recorded "show all" decision (not a clear).
    setHitCriteria.mutate(
      { runId, criteria: state.rules },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Hit Criteria for this Run</DialogTitle>
          <DialogDescription>
            Define up to {MAX_RULES} rules (combined with AND) to classify this run's hits. This is
            recorded as your decision for this run, independent of the protocol recommendation.
            Saving with no rules records "show all compounds".
          </DialogDescription>
        </DialogHeader>

        <HitCriteriaRulesEditor state={state} readoutDefinitions={readoutDefinitions} />

        <DialogFooter>
          {/* Reset clears the run's recorded decision so it reverts to "unset"
              and the protocol recommendation is shown again. Only meaningful
              when the run already has a recorded decision. */}
          {currentCriteria !== null && (
            <Button
              variant="ghost"
              className="mr-auto text-muted-foreground"
              onClick={() =>
                resetHitCriteria.mutate(runId, { onSuccess: () => onOpenChange(false) })
              }
              disabled={resetHitCriteria.isPending || setHitCriteria.isPending}
            >
              <RotateCcw className="mr-1.5 h-4 w-4" /> Reset to protocol recommendation
            </Button>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={setHitCriteria.isPending || (!state.isValid && state.rules.length > 0)}
          >
            {setHitCriteria.isPending ? "Saving..." : "Save for this Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
