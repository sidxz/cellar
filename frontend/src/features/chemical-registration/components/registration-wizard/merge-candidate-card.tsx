"use client";

import { useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import {
  Card,
  CardContent,
} from "@/shared/components/ui/card";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import { useMolecule } from "../../hooks/use-molecules";
import { useMergeImpact } from "../../hooks/use-disclosures";
import type { MergeCandidateRef } from "../../types/registration-wizard";
import { ImpactRow } from "../merge-impact-row";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MergeCandidateCardProps {
  candidate: MergeCandidateRef;
  decision: "confirm" | "reject";
  onDecisionChange: (decision: "confirm" | "reject") => void;
  disabled?: boolean;
}

// ---------------------------------------------------------------------------
// MergeCandidateCard
// ---------------------------------------------------------------------------

export function MergeCandidateCard({
  candidate,
  decision,
  onDecisionChange,
  disabled = false,
}: MergeCandidateCardProps) {
  const [showImpact, setShowImpact] = useState(false);

  const sourceQuery = useMolecule(candidate.molecule_id);
  const targetQuery = useMolecule(candidate.matched_molecule_id);

  // Only fetch impact when expanded
  const impactQuery = useMergeImpact(
    showImpact ? candidate.molecule_id : undefined,
    showImpact ? candidate.matched_molecule_id : undefined
  );

  const source = sourceQuery.data;
  const target = targetQuery.data;
  const impact = impactQuery.data;
  const hasBlockers = (impact?.blockers?.length ?? 0) > 0;
  const isConfirmed = decision === "confirm";

  return (
    <Card className={disabled ? "opacity-60" : undefined}>
      <CardContent className="py-4">
        {/* Top row: checkbox + molecule names */}
        <div className="flex items-center gap-3">
          <Checkbox
            checked={isConfirmed}
            disabled={disabled}
            onCheckedChange={(checked) =>
              onDecisionChange(checked ? "confirm" : "reject")
            }
            aria-label={`Confirm merge for row ${candidate.row_index}`}
          />

          <div className="flex flex-1 items-center gap-2 min-w-0">
            {/* Source */}
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">
                {source?.name ?? "Loading..."}
              </div>
              <div className="text-xs text-muted-foreground font-mono">
                {source?.registration_number ?? "..."}
              </div>
            </div>

            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />

            {/* Target */}
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">
                {target?.name ?? "Loading..."}
              </div>
              <div className="text-xs text-muted-foreground font-mono">
                {target?.registration_number ?? "..."}
              </div>
            </div>
          </div>

          <Badge variant={isConfirmed ? "default" : "outline"} className="shrink-0">
            {isConfirmed ? "Merge" : "Skip"}
          </Badge>
        </div>

        {/* Expandable impact section */}
        <Collapsible open={showImpact} onOpenChange={setShowImpact}>
          <CollapsibleTrigger className="mt-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <ChevronDown
              className={`h-3 w-3 transition-transform ${showImpact ? "rotate-180" : ""}`}
            />
            {showImpact ? "Hide impact details" : "Show impact details"}
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            {impactQuery.isLoading && (
              <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading impact...
              </div>
            )}

            {impact && impact.categories.length > 0 && (
              <div className="space-y-1 rounded-md border p-2">
                {impact.categories.map((cat) => (
                  <ImpactRow key={cat.name} category={cat} />
                ))}
              </div>
            )}

            {impact && impact.categories.length === 0 && (
              <div className="py-2 text-xs text-muted-foreground">
                No data associated with the source compound.
              </div>
            )}

            {/* Blockers */}
            {hasBlockers && (
              <div className="mt-2 flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/5 p-3">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                <div className="space-y-1">
                  <p className="text-xs font-medium text-destructive">
                    Merge blocked
                  </p>
                  {impact!.blockers.map((b, i) => (
                    <p key={i} className="text-xs text-destructive/80">
                      {b}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
