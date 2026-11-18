"use client";

import { MemberName } from "@/shared/components/entity-name";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { formatDate } from "@/shared/lib/format-date";
import { useState } from "react";
import { useSetRunHitCriteria } from "../hooks/use-runs";
import { type ApplicableRule, runRulesOf } from "../lib/melt-hits";
import type { HitCriterion, ReadoutDefinition, Run } from "../types";
import { criterionLabel } from "./detail-tabs/use-activity-tab";
import { RunHitCriteriaDialog } from "./hit-criteria-dialog";

const labels = (rules: readonly HitCriterion[]) => rules.map(criterionLabel).join(" and ");

/** The run's hit rule above the thermal shift results: the recorded decision
 *  with who and when, or the protocol's recommendation (never applied by
 *  itself), and the rules this page does not evaluate. */
export function MeltHitRule({
  run,
  readoutDefinitions,
  recommendation,
  applicable,
  other,
  canEdit,
  compact = false,
}: {
  run: Pick<
    Run,
    "id" | "is_locked" | "hit_criteria" | "hit_criteria_set_by" | "hit_criteria_set_at"
  >;
  readoutDefinitions: ReadoutDefinition[];
  recommendation: HitCriterion[] | null;
  /** The run's rules on Tm/ΔTm readouts. */
  applicable: readonly ApplicableRule[];
  /** The run's other rules, listed but not evaluated here. */
  other: readonly HitCriterion[];
  canEdit: boolean;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const setHitCriteria = useSetRunHitCriteria();
  const recorded = run.hit_criteria ?? null;
  const { kept: recommended, dropped } = runRulesOf(recommendation ?? [], readoutDefinitions);

  const setBy = run.hit_criteria_set_by && (
    <span className="text-xs text-muted-foreground">
      · Set by <MemberName id={run.hit_criteria_set_by} />
      {run.hit_criteria_set_at ? ` on ${formatDate(run.hit_criteria_set_at)}` : ""}
    </span>
  );
  const button = (label: string, onClick: () => void, variant: "default" | "outline" = "outline") =>
    canEdit && (
      <Button
        type="button"
        size="sm"
        variant={variant}
        disabled={run.is_locked || setHitCriteria.isPending}
        title={run.is_locked ? "This run is locked" : undefined}
        onClick={onClick}
      >
        {label}
      </Button>
    );
  const edit = button("Edit", () => setOpen(true));

  let line: React.ReactNode;
  const leftOut = recorded === null && dropped.length > 0 && (
    <p className="text-xs text-muted-foreground">
      {`Left out (a series value is not a run rule): ${labels(dropped)}`}
    </p>
  );
  if (recorded === null && recommended.length > 0) {
    line = (
      <>
        <span className="font-medium">{`Protocol recommends: ${labels(recommended)}`}</span>
        <span className="text-xs text-muted-foreground">Not yet applied</span>
        {button(
          "Apply to this run",
          () => setHitCriteria.mutate({ runId: run.id, criteria: recommended }),
          "default",
        )}
        {button("Customize…", () => setOpen(true))}
      </>
    );
  } else if (recorded === null) {
    line = (
      <>
        <span className="text-muted-foreground">No hit rule for this run</span>
        {button("Set hit rule", () => setOpen(true))}
      </>
    );
  } else if (recorded.length === 0) {
    line = (
      <>
        <span className="text-muted-foreground">No hit rule (show all)</span>
        {setBy}
        {edit}
      </>
    );
  } else if (applicable.length === 0) {
    line = (
      <>
        <span className="text-muted-foreground">No hit rule on Tm or ΔTm for this run</span>
        {setBy}
        {edit}
      </>
    );
  } else {
    line = (
      <>
        <span className="font-medium">{`Hit rule: ${labels(applicable.map((a) => a.rule))}`}</span>
        {setBy}
        {edit}
      </>
    );
  }

  const details = (
    <div className="space-y-1 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">{line}</div>
      {leftOut}
      {other.length > 0 && (
        <p className="text-xs text-muted-foreground">{`Not evaluated here: ${labels(other)}`}</p>
      )}
    </div>
  );
  return (
    <>
      {compact ? (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label="Hit rule details"
              className="text-left text-sm hover:text-primary"
            >
              <span className="font-medium">
                {recorded === null
                  ? "Not set"
                  : recorded.length === 0
                    ? "Show all"
                    : applicable.length
                      ? labels(applicable.map((a) => a.rule))
                      : "Other readouts"}
              </span>
              <span className="ml-2 text-xs text-primary">
                {canEdit && !run.is_locked ? (recorded === null ? "Configure" : "Edit") : "Details"}
              </span>
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-96 max-w-[90vw]">
            {details}
          </PopoverContent>
        </Popover>
      ) : (
        details
      )}
      {canEdit && (
        <RunHitCriteriaDialog
          runId={run.id}
          readoutDefinitions={readoutDefinitions}
          currentCriteria={recorded}
          recommendation={recommendation}
          open={open}
          onOpenChange={setOpen}
        />
      )}
    </>
  );
}
