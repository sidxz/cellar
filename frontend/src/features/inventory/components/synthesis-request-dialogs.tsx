"use client";

import { useSynthesisRoutesByMolecule } from "@/features/chemical-registration/hooks/use-synthesis-routes";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { MemberSelector } from "@/shared/components/member-selector";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { cn } from "@/shared/lib/utils";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { useBatchesByMolecule } from "../hooks/use-batches";
import type {
  useAssignSynthesisRequest,
  useCompleteSynthesis,
  useFailSynthesis,
  useFlagInfeasible,
  useFulfillSynthesisRequest,
  useRejectSynthesisRequest,
  useStartSynthesis,
  useUpdateSynthesisRequest,
} from "../hooks/use-synthesis-requests";
import {
  FEASIBILITY_STATUS_LABELS,
  type FeasibilityStatus,
  type SynthesisRequest,
} from "../types/synthesis-request";

export function EditSynthesisRequestDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useUpdateSynthesisRequest>;
}) {
  const [purpose, setPurpose] = useState(request.purpose);
  const [priority, setPriority] = useState(request.priority);
  const [amountValue, setAmountValue] = useState(String(request.amount_value));
  const [amountUnit, setAmountUnit] = useState(request.amount_unit);
  const [targetPurity, setTargetPurity] = useState(
    request.target_purity != null ? String(request.target_purity) : "",
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setPurpose(request.purpose);
          setPriority(request.priority);
          setAmountValue(String(request.amount_value));
          setAmountUnit(request.amount_unit);
          setTargetPurity(request.target_purity != null ? String(request.target_purity) : "");
        }
        onOpenChange(v);
      }}
    >
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Edit Synthesis Request</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="edit-synreq-purpose">Purpose</Label>
            <Textarea
              id="edit-synreq-purpose"
              rows={3}
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-synreq-priority">Priority</Label>
            <Select value={priority} onValueChange={setPriority}>
              <SelectTrigger id="edit-synreq-priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="routine">Routine</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="edit-synreq-amount">Amount</Label>
              <Input
                id="edit-synreq-amount"
                type="number"
                min={0}
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-synreq-unit">Unit</Label>
              <select
                id="edit-synreq-unit"
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={amountUnit}
                onChange={(e) => setAmountUnit(e.target.value)}
              >
                <option value="mg">mg</option>
                <option value="g">g</option>
                <option value="mL">mL</option>
                <option value="L">L</option>
              </select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-synreq-purity">Target Purity (%)</Label>
            <Input
              id="edit-synreq-purity"
              type="number"
              min={0}
              max={100}
              step={0.1}
              placeholder="e.g. 95.0"
              value={targetPurity}
              onChange={(e) => setTargetPurity(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  purpose: purpose.trim(),
                  priority,
                  amount_value: Number.parseFloat(amountValue) || request.amount_value,
                  amount_unit: amountUnit,
                  target_purity: targetPurity ? Number.parseFloat(targetPurity) : null,
                },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={!purpose.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RejectDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useRejectSynthesisRequest>;
}) {
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Reject Request</DialogTitle>
          <DialogDescription>
            Provide a reason for rejecting this synthesis request.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Reason</Label>
          <Textarea
            placeholder="e.g., starting material not available"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
          />
        </div>
        <DialogFooter>
          <Button
            variant="destructive"
            onClick={() => {
              mutation.mutate({ id: request.id, reason }, { onSuccess: () => onOpenChange(false) });
            }}
            disabled={!reason.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Rejecting..." : "Reject"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AssignDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useAssignSynthesisRequest>;
}) {
  const [assignmentType, setAssignmentType] = useState("internal");
  const [assignedToId, setAssignedToId] = useState<string | null>(null);
  const [assignedOrgId, setAssignedOrgId] = useState("");

  const { data: organizations, isLoading: orgsLoading } = useOrganizations();

  const isValid =
    (assignmentType === "internal" && assignedToId !== null) ||
    (assignmentType === "cro" && assignedOrgId.trim() !== "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Assign Request</DialogTitle>
          <DialogDescription>Assign this synthesis request to a chemist or CRO.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Assignment Type</Label>
            <Select
              value={assignmentType}
              onValueChange={(v) => {
                setAssignmentType(v);
                setAssignedToId(null);
                setAssignedOrgId("");
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="internal">Internal Chemist</SelectItem>
                <SelectItem value="cro">External CRO</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {assignmentType === "internal" && (
            <div className="grid gap-2">
              <Label>Assignee</Label>
              <MemberSelector
                selectedId={assignedToId}
                onSelect={setAssignedToId}
                placeholder="Search team members..."
              />
            </div>
          )}
          {assignmentType === "cro" && (
            <div className="grid gap-2">
              <Label htmlFor="assign-org">CRO Organization</Label>
              <Select value={assignedOrgId} onValueChange={setAssignedOrgId} disabled={orgsLoading}>
                <SelectTrigger id="assign-org">
                  <SelectValue
                    placeholder={orgsLoading ? "Loading organizations..." : "Select CRO..."}
                  />
                </SelectTrigger>
                <SelectContent>
                  {organizations?.map((org) => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  assignment_type: assignmentType,
                  assigned_to: assignmentType === "internal" ? assignedToId : null,
                  assigned_org_id:
                    assignmentType === "cro" && assignedOrgId.trim() ? assignedOrgId.trim() : null,
                },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={mutation.isPending || !isValid}
          >
            {mutation.isPending ? "Assigning..." : "Assign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function StartDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useStartSynthesis>;
}) {
  const [proposedRouteId, setProposedRouteId] = useState("");

  const {
    data: routes,
    isLoading: routesLoading,
    refetch: refetchRoutes,
  } = useSynthesisRoutesByMolecule(request.molecule_id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Start Synthesis</DialogTitle>
          <DialogDescription>
            Begin synthesis. Optionally link a proposed synthesis route.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label htmlFor="start-route">Proposed Route (optional)</Label>
          <div className="flex gap-2">
            <Select
              value={proposedRouteId}
              onValueChange={setProposedRouteId}
              disabled={routesLoading}
            >
              <SelectTrigger id="start-route" className="flex-1">
                <SelectValue
                  placeholder={routesLoading ? "Loading routes..." : "None — start without a route"}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {routes?.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.name}
                    {r.status !== "draft" ? ` (${r.status})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => refetchRoutes()}
              disabled={routesLoading}
              title="Refresh routes"
            >
              <RefreshCw className={cn("h-4 w-4", routesLoading && "animate-spin")} />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {!routesLoading && (!routes || routes.length === 0)
              ? "No routes found for this molecule. "
              : ""}
            <a
              href={`/compounds/${request.molecule_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              Manage routes on compound page &rarr;
            </a>
          </p>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  proposed_route_id:
                    proposedRouteId && proposedRouteId !== "none" ? proposedRouteId : null,
                },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Starting..." : "Start Synthesis"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function FlagInfeasibleDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useFlagInfeasible>;
}) {
  const [feasibilityStatus, setFeasibilityStatus] = useState<FeasibilityStatus>("infeasible");
  const [notes, setNotes] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Flag Feasibility</DialogTitle>
          <DialogDescription>
            Record the feasibility assessment for this synthesis request.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Feasibility Status</Label>
            <Select
              value={feasibilityStatus}
              onValueChange={(v) => setFeasibilityStatus(v as FeasibilityStatus)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(FEASIBILITY_STATUS_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Notes (optional)</Label>
            <Textarea
              placeholder="Additional context or alternative proposals"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  feasibility_status: feasibilityStatus,
                  feasibility_notes: notes.trim() || null,
                },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Save Assessment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function CompleteDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useCompleteSynthesis>;
}) {
  const [actualCostValue, setActualCostValue] = useState("");
  const [actualCostUnit, setActualCostUnit] = useState("USD");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Complete Synthesis</DialogTitle>
          <DialogDescription>
            Mark synthesis as complete. Optionally record the actual cost.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Actual Cost (optional)</Label>
              <Input
                type="number"
                placeholder="0.00"
                value={actualCostValue}
                onChange={(e) => setActualCostValue(e.target.value)}
                min={0}
              />
            </div>
            <div className="grid gap-2">
              <Label>Currency</Label>
              <Select value={actualCostUnit} onValueChange={setActualCostUnit}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="USD">USD</SelectItem>
                  <SelectItem value="EUR">EUR</SelectItem>
                  <SelectItem value="GBP">GBP</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  actual_cost_value:
                    actualCostValue !== "" ? Number.parseFloat(actualCostValue) : null,
                  actual_cost_unit: actualCostValue !== "" ? actualCostUnit : null,
                },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Completing..." : "Complete Synthesis"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function FulfillDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useFulfillSynthesisRequest>;
}) {
  const [batchId, setBatchId] = useState("");

  const { data: batches, isLoading: batchesLoading } = useBatchesByMolecule(request.molecule_id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Fulfill Request</DialogTitle>
          <DialogDescription>
            Select the synthesized batch to fulfill this request.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label htmlFor="fulfill-batch">Batch</Label>
          <Select value={batchId} onValueChange={setBatchId} disabled={batchesLoading}>
            <SelectTrigger id="fulfill-batch">
              <SelectValue
                placeholder={batchesLoading ? "Loading batches..." : "Select batch..."}
              />
            </SelectTrigger>
            <SelectContent>
              {batches?.map((b) => (
                <SelectItem key={b.id} value={b.id}>
                  {b.batch_number}
                  {b.purity != null ? ` — ${b.purity}% purity` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {!batchesLoading && (!batches || batches.length === 0) && (
            <p className="text-xs text-muted-foreground">
              No batches found for this molecule. Register the synthesized batch first.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { id: request.id, batch_id: batchId },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={!batchId || mutation.isPending}
          >
            {mutation.isPending ? "Fulfilling..." : "Fulfill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function FailDialog({
  request,
  open,
  onOpenChange,
  mutation,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutation: ReturnType<typeof useFailSynthesis>;
}) {
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Mark as Failed</DialogTitle>
          <DialogDescription>Record the reason for synthesis failure.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Reason</Label>
          <Textarea
            placeholder="e.g., reaction yield too low, reagent contaminated"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
          />
        </div>
        <DialogFooter>
          <Button
            variant="destructive"
            onClick={() => {
              mutation.mutate({ id: request.id, reason }, { onSuccess: () => onOpenChange(false) });
            }}
            disabled={!reason.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Mark Failed"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
