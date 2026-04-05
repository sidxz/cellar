"use client";

import { useMemo, useState } from "react";
import { X, GitBranch } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { MemberName } from "@/shared/components/entity-name";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Textarea } from "@/shared/components/ui/textarea";
import {
  useSynthesisRoute,
  useValidateSynthesisRoute,
  useSetPreferredRoute,
  useDeprecateSynthesisRoute,
} from "../hooks/use-synthesis-routes";
import {
  ROUTE_STATUS_LABELS,
  ROUTE_TYPE_LABELS,
  ROUTE_SCALE_LABELS,
  type RouteStatus,
  type ReactionStep,
  type ReactionReagent,
} from "../types/synthesis-route";

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function routeStatusVariant(
  s: RouteStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (s) {
    case "preferred":
      return "default";
    case "validated":
      return "secondary";
    case "deprecated":
      return "destructive";
    default:
      return "outline";
  }
}

// ---------------------------------------------------------------------------
// Deprecate dialog
// ---------------------------------------------------------------------------

interface DeprecateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string | null) => void;
  isPending: boolean;
}

function DeprecateDialog({
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: DeprecateDialogProps) {
  const [reason, setReason] = useState("");

  const handleConfirm = () => {
    onConfirm(reason.trim() || null);
    setReason("");
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) setReason("");
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Deprecate Route</DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <Label htmlFor="deprecate-reason">Reason (optional)</Label>
          <Textarea
            id="deprecate-reason"
            className="mt-2"
            placeholder="e.g. Superseded by Route B with improved yield"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending ? "Deprecating..." : "Deprecate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Reagent row
// ---------------------------------------------------------------------------

function ReagentRow({ reagent }: { reagent: ReactionReagent }) {
  return (
    <div className="flex items-center gap-3 rounded border px-3 py-2 text-sm">
      <Badge variant="outline" className="shrink-0 text-xs">
        {reagent.role}
      </Badge>
      <span className="flex-1 font-medium">{reagent.name}</span>
      {reagent.cas_number && (
        <span className="font-mono text-xs text-muted-foreground">
          CAS {reagent.cas_number}
        </span>
      )}
      {reagent.equivalents != null && (
        <span className="text-xs text-muted-foreground">
          {reagent.equivalents} eq
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step card
// ---------------------------------------------------------------------------

function StepCard({ step, stepNumberById }: { step: ReactionStep; stepNumberById: Map<string, number> }) {
  const conditions = step.conditions as Record<string, unknown> | null;
  const outcome = step.outcome as Record<string, unknown> | null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
              {step.step_number}
            </span>
            <CardTitle className="text-base">
              {step.name ?? step.named_reaction ?? `Step ${step.step_number}`}
            </CardTitle>
          </div>
          {step.branch_label && (
            <Badge variant="outline" className="text-xs">
              {step.branch_label}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Product */}
        {step.product_description && (
          <div>
            <p className="text-xs font-medium text-muted-foreground">Product</p>
            <p className="mt-0.5 text-sm">{step.product_description}</p>
          </div>
        )}

        {/* Reaction SMILES */}
        {step.reaction_smiles && (
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              Reaction SMILES
            </p>
            <p className="mt-0.5 break-all font-mono text-xs text-muted-foreground">
              {step.reaction_smiles}
            </p>
          </div>
        )}

        {/* Conditions */}
        {conditions && Object.keys(conditions).length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Conditions
            </p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg border p-2 text-sm sm:grid-cols-3">
              {Object.entries(conditions).map(([k, v]) => (
                <div key={k}>
                  <p className="text-xs text-muted-foreground">
                    {k.replace(/_/g, " ")}
                  </p>
                  <p className="font-medium">{String(v)}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Outcome */}
        {outcome && Object.keys(outcome).length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Outcome
            </p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg border p-2 text-sm sm:grid-cols-3">
              {Object.entries(outcome).map(([k, v]) => (
                <div key={k}>
                  <p className="text-xs text-muted-foreground">
                    {k.replace(/_/g, " ")}
                  </p>
                  <p className="font-medium">
                    {typeof v === "number" ? v.toFixed(1) : String(v)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Reagents */}
        {step.reagents.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Reagents ({step.reagents.length})
            </p>
            <div className="space-y-1">
              {step.reagents.map((r, i) => (
                <ReagentRow key={i} reagent={r} />
              ))}
            </div>
          </div>
        )}

        {/* Preceding steps */}
        {step.preceding_step_ids.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Follows steps:</span>
            {step.preceding_step_ids.map((sid) => (
              <Badge key={sid} variant="outline" className="text-xs">
                Step {stepNumberById.get(sid) ?? "?"}
              </Badge>
            ))}
          </div>
        )}

        {/* Notes */}
        {step.notes && (
          <p className="rounded bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {step.notes}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SynthesisRouteDetail
// ---------------------------------------------------------------------------

interface SynthesisRouteDetailProps {
  routeId: string;
  onClose?: () => void;
}

export function SynthesisRouteDetail({
  routeId,
  onClose,
}: SynthesisRouteDetailProps) {
  const { data: route, isLoading } = useSynthesisRoute(routeId);
  const validateMutation = useValidateSynthesisRoute();
  const preferMutation = useSetPreferredRoute();
  const deprecateMutation = useDeprecateSynthesisRoute();

  const [deprecateOpen, setDeprecateOpen] = useState(false);

  // --- Loading ---
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  // --- Not found ---
  if (!route) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
        <GitBranch className="h-10 w-10 text-muted-foreground/40" />
        <p className="mt-4 text-sm">Synthesis route not found.</p>
      </div>
    );
  }

  const status = route.status as RouteStatus;

  const handleDeprecate = (reason: string | null) => {
    deprecateMutation.mutate(
      { id: routeId, reason },
      { onSuccess: () => setDeprecateOpen(false) }
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">{route.name}</h2>
            <Badge variant={routeStatusVariant(status)}>
              {ROUTE_STATUS_LABELS[status] ?? status}
            </Badge>
            <Badge variant="outline">
              {ROUTE_TYPE_LABELS[route.route_type] ?? route.route_type}
            </Badge>
            {route.scale && (
              <Badge variant="outline">
                {ROUTE_SCALE_LABELS[route.scale] ?? route.scale}
              </Badge>
            )}
          </div>
          {route.description && (
            <p className="text-sm text-muted-foreground">{route.description}</p>
          )}
        </div>
        {onClose && (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Metadata */}
      <Card>
        <CardContent className="grid grid-cols-2 gap-4 pt-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Source</p>
            <p className="font-medium capitalize">
              {route.source.replace(/_/g, " ")}
            </p>
          </div>
          {route.source_reference && (
            <div>
              <p className="text-xs text-muted-foreground">Reference</p>
              <p className="font-medium">{route.source_reference}</p>
            </div>
          )}
          <div>
            <p className="text-xs text-muted-foreground">Overall Yield</p>
            <p className="font-medium">
              {route.overall_yield != null
                ? `${route.overall_yield.toFixed(1)}%`
                : "\u2014"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Steps</p>
            <p className="font-medium">{route.total_steps}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Created By</p>
            <p className="font-medium text-sm"><MemberName id={route.created_by} /></p>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      {status !== "deprecated" && (
        <div className="flex flex-wrap gap-2">
          {status === "draft" && (
            <Button
              size="sm"
              onClick={() => validateMutation.mutate(routeId)}
              disabled={validateMutation.isPending}
            >
              {validateMutation.isPending ? "Validating..." : "Validate"}
            </Button>
          )}
          {status === "validated" && (
            <>
              <Button
                size="sm"
                onClick={() => preferMutation.mutate(routeId)}
                disabled={preferMutation.isPending}
              >
                {preferMutation.isPending ? "Setting..." : "Set Preferred"}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setDeprecateOpen(true)}
              >
                Deprecate
              </Button>
            </>
          )}
          {status === "preferred" && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setDeprecateOpen(true)}
            >
              Deprecate
            </Button>
          )}
        </div>
      )}

      {/* Steps */}
      <div className="space-y-3">
        <h3 className="text-base font-semibold">
          Reaction Steps
          {route.steps.length > 0 && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({route.steps.length})
            </span>
          )}
        </h3>
        {route.steps.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No steps added yet.
          </p>
        ) : (
          <div className="space-y-3">
            {(() => {
              const sorted = route.steps.slice().sort((a, b) => a.step_number - b.step_number);
              const idMap = new Map(sorted.map((s) => [s.id, s.step_number]));
              return sorted.map((step) => (
                <StepCard key={step.id} step={step} stepNumberById={idMap} />
              ));
            })()}
          </div>
        )}
      </div>

      <DeprecateDialog
        open={deprecateOpen}
        onOpenChange={setDeprecateOpen}
        onConfirm={handleDeprecate}
        isPending={deprecateMutation.isPending}
      />
    </div>
  );
}
