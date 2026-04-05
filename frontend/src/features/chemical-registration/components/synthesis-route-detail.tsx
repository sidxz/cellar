"use client";

import { useMemo, useState } from "react";
import { X, GitBranch, Plus, FlaskConical, Pencil, Trash2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { MemberName } from "@/shared/components/entity-name";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Textarea } from "@/shared/components/ui/textarea";
import {
  useSynthesisRoute,
  useAddReactionStep,
  useRecordStepOutcome,
  useValidateSynthesisRoute,
  useSetPreferredRoute,
  useDeprecateSynthesisRoute,
  useUpdateSynthesisRoute,
  useDeleteSynthesisRoute,
  useRemoveReactionStep,
} from "../hooks/use-synthesis-routes";
import {
  ROUTE_STATUS_LABELS,
  ROUTE_TYPE_LABELS,
  ROUTE_SCALE_LABELS,
  type RouteStatus,
  type ReactionStep,
  type ReactionReagent,
  type AddReactionStepInput,
  type RecordStepOutcomeInput,
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
// Edit route dialog
// ---------------------------------------------------------------------------

interface EditRouteDialogProps {
  route: {
    id: string;
    name: string;
    description: string | null;
    scale: string | null;
  };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function EditRouteDialog({ route, open, onOpenChange }: EditRouteDialogProps) {
  const mutation = useUpdateSynthesisRoute();
  const [name, setName] = useState(route.name);
  const [description, setDescription] = useState(route.description ?? "");
  const [scale, setScale] = useState(route.scale ?? "");

  const handleSave = () => {
    mutation.mutate(
      {
        id: route.id,
        name: name.trim(),
        description: description.trim() || null,
        scale: scale || null,
      },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setName(route.name);
          setDescription(route.description ?? "");
          setScale(route.scale ?? "");
        }
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Edit Route</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label htmlFor="edit-route-name">Name *</Label>
            <Input
              id="edit-route-name"
              className="mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="edit-route-description">Description</Label>
            <Textarea
              id="edit-route-description"
              className="mt-1"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="edit-route-scale">Scale</Label>
            <Select value={scale} onValueChange={setScale}>
              <SelectTrigger id="edit-route-scale" className="mt-1">
                <SelectValue placeholder="Select scale..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {Object.entries(ROUTE_SCALE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Add step dialog
// ---------------------------------------------------------------------------

interface AddStepDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  routeId: string;
  nextStepNumber: number;
}

function AddStepDialog({
  open,
  onOpenChange,
  routeId,
  nextStepNumber,
}: AddStepDialogProps) {
  const [stepNumber, setStepNumber] = useState(nextStepNumber);
  const [name, setName] = useState("");
  const [namedReaction, setNamedReaction] = useState("");
  const [reactionSmiles, setReactionSmiles] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [notes, setNotes] = useState("");

  const addStepMutation = useAddReactionStep(routeId);

  const resetForm = () => {
    setStepNumber(nextStepNumber);
    setName("");
    setNamedReaction("");
    setReactionSmiles("");
    setProductDescription("");
    setNotes("");
  };

  const handleSubmit = () => {
    const data: AddReactionStepInput = {
      step_number: stepNumber,
      name: name.trim() || null,
      named_reaction: namedReaction.trim() || null,
      reaction_smiles: reactionSmiles.trim() || null,
      product_description: productDescription.trim() || null,
      notes: notes.trim() || null,
    };

    addStepMutation.mutate(data, {
      onSuccess: () => {
        resetForm();
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) resetForm();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Add Reaction Step</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label htmlFor="add-step-number">Step Number *</Label>
            <Input
              id="add-step-number"
              type="number"
              min={1}
              className="mt-1"
              value={stepNumber}
              onChange={(e) => setStepNumber(parseInt(e.target.value) || 1)}
            />
          </div>
          <div>
            <Label htmlFor="add-step-name">Name</Label>
            <Input
              id="add-step-name"
              className="mt-1"
              placeholder="e.g. Suzuki coupling"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="add-step-named-reaction">Named Reaction</Label>
            <Input
              id="add-step-named-reaction"
              className="mt-1"
              placeholder="e.g. Suzuki-Miyaura"
              value={namedReaction}
              onChange={(e) => setNamedReaction(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="add-step-smiles">Reaction SMILES</Label>
            <Input
              id="add-step-smiles"
              className="mt-1"
              placeholder="SMILES string"
              value={reactionSmiles}
              onChange={(e) => setReactionSmiles(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="add-step-product">Product Description</Label>
            <Input
              id="add-step-product"
              className="mt-1"
              placeholder="e.g. Biaryl intermediate"
              value={productDescription}
              onChange={(e) => setProductDescription(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="add-step-notes">Notes</Label>
            <Textarea
              id="add-step-notes"
              className="mt-1"
              rows={3}
              placeholder="Additional notes for this step"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={addStepMutation.isPending}>
            {addStepMutation.isPending ? "Adding..." : "Add Step"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Record outcome dialog
// ---------------------------------------------------------------------------

interface RecordOutcomeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  routeId: string;
  stepId: string;
  stepLabel: string;
}

function RecordOutcomeDialog({
  open,
  onOpenChange,
  routeId,
  stepId,
  stepLabel,
}: RecordOutcomeDialogProps) {
  const [yieldPercent, setYieldPercent] = useState("");
  const [purityPercent, setPurityPercent] = useState("");
  const [purificationMethod, setPurificationMethod] = useState("");

  const recordOutcomeMutation = useRecordStepOutcome(routeId, stepId);

  const resetForm = () => {
    setYieldPercent("");
    setPurityPercent("");
    setPurificationMethod("");
  };

  const handleSubmit = () => {
    const data: RecordStepOutcomeInput = {
      yield_percent: yieldPercent ? parseFloat(yieldPercent) : null,
      purity_percent: purityPercent ? parseFloat(purityPercent) : null,
      purification_method: purificationMethod.trim() || null,
    };

    recordOutcomeMutation.mutate(data, {
      onSuccess: () => {
        resetForm();
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) resetForm();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Record Outcome &mdash; {stepLabel}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label htmlFor="outcome-yield">Yield (%)</Label>
            <Input
              id="outcome-yield"
              type="number"
              min={0}
              max={100}
              step={0.1}
              className="mt-1"
              placeholder="e.g. 85.0"
              value={yieldPercent}
              onChange={(e) => setYieldPercent(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="outcome-purity">Purity (%)</Label>
            <Input
              id="outcome-purity"
              type="number"
              min={0}
              max={100}
              step={0.1}
              className="mt-1"
              placeholder="e.g. 97.5"
              value={purityPercent}
              onChange={(e) => setPurityPercent(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="outcome-purification">Purification Method</Label>
            <Input
              id="outcome-purification"
              className="mt-1"
              placeholder="e.g. Column chromatography"
              value={purificationMethod}
              onChange={(e) => setPurificationMethod(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={recordOutcomeMutation.isPending}
          >
            {recordOutcomeMutation.isPending ? "Saving..." : "Save Outcome"}
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

function StepCard({
  step,
  stepNumberById,
  routeId,
  routeStatus,
  onRemove,
}: {
  step: ReactionStep;
  stepNumberById: Map<string, number>;
  routeId: string;
  routeStatus: string;
  onRemove?: (stepId: string) => void;
}) {
  const conditions = step.conditions as Record<string, unknown> | null;
  const outcome = step.outcome as Record<string, unknown> | null;
  const [outcomeOpen, setOutcomeOpen] = useState(false);

  const canRecordOutcome =
    (routeStatus === "draft" || routeStatus === "validated") && !outcome;

  const stepLabel = step.name ?? step.named_reaction ?? `Step ${step.step_number}`;

  return (
    <>
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
              {step.step_number}
            </span>
            <CardTitle className="text-base">
              {stepLabel}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {routeStatus === "draft" && onRemove && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-destructive hover:text-destructive"
                onClick={() => {
                  if (confirm(`Remove step "${stepLabel}"? This cannot be undone.`)) {
                    onRemove(step.id);
                  }
                }}
              >
                <Trash2 className="mr-1 h-3 w-3" />
                Remove
              </Button>
            )}
            {canRecordOutcome && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => setOutcomeOpen(true)}
              >
                <FlaskConical className="mr-1 h-3 w-3" />
                Record Outcome
              </Button>
            )}
            {step.branch_label && (
              <Badge variant="outline" className="text-xs">
                {step.branch_label}
              </Badge>
            )}
          </div>
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

    {canRecordOutcome && (
      <RecordOutcomeDialog
        open={outcomeOpen}
        onOpenChange={setOutcomeOpen}
        routeId={routeId}
        stepId={step.id}
        stepLabel={stepLabel}
      />
    )}
    </>
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
  const deleteMutation = useDeleteSynthesisRoute();
  const removeStepMutation = useRemoveReactionStep(routeId);

  const [deprecateOpen, setDeprecateOpen] = useState(false);
  const [addStepOpen, setAddStepOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

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
        <div className="flex shrink-0 items-center gap-1">
          {status === "draft" && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditOpen(true)}
              >
                <Pencil className="mr-1 h-3.5 w-3.5" />
                Edit
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  if (confirm("Delete this route? This cannot be undone.")) {
                    deleteMutation.mutate(routeId, {
                      onSuccess: () => onClose?.(),
                    });
                  }
                }}
                disabled={deleteMutation.isPending}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                {deleteMutation.isPending ? "Deleting..." : "Delete"}
              </Button>
            </>
          )}
          {onClose && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
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
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">
            Reaction Steps
            {route.steps.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({route.steps.length})
              </span>
            )}
          </h3>
          {status === "draft" && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setAddStepOpen(true)}
            >
              <Plus className="mr-1 h-4 w-4" />
              Add Step
            </Button>
          )}
        </div>
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
                <StepCard
                  key={step.id}
                  step={step}
                  stepNumberById={idMap}
                  routeId={routeId}
                  routeStatus={status}
                  onRemove={(stepId) => removeStepMutation.mutate(stepId)}
                />
              ));
            })()}
          </div>
        )}
      </div>

      {status === "draft" && (
        <EditRouteDialog
          route={route}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}

      <DeprecateDialog
        open={deprecateOpen}
        onOpenChange={setDeprecateOpen}
        onConfirm={handleDeprecate}
        isPending={deprecateMutation.isPending}
      />

      {status === "draft" && (
        <AddStepDialog
          open={addStepOpen}
          onOpenChange={setAddStepOpen}
          routeId={routeId}
          nextStepNumber={route.steps.length + 1}
        />
      )}
    </div>
  );
}
