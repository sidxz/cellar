"use client";

import { useState } from "react";
import { ArrowLeft, FlaskRound } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/shared/components/ui/badge";
import { MemberSelector } from "@/shared/components/member-selector";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
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
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Textarea } from "@/shared/components/ui/textarea";
import { MoleculeName, OrgName, MemberName, BatchName, RouteName } from "@/shared/components/entity-name";
import {
  useSynthesisRequest,
  useSubmitSynthesisRequest,
  useApproveSynthesisRequest,
  useRejectSynthesisRequest,
  useAssignSynthesisRequest,
  useStartSynthesis,
  useFlagInfeasible,
  useCompleteSynthesis,
  useFulfillSynthesisRequest,
  useFailSynthesis,
  useCancelSynthesisRequest,
} from "../hooks/use-synthesis-requests";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useSynthesisRoutesByMolecule } from "@/features/chemical-registration/hooks/use-synthesis-routes";
import {
  SYNTHESIS_REQUEST_STATUS_LABELS,
  FEASIBILITY_STATUS_LABELS,
  type SynthesisRequest,
  type SynthesisRequestStatus,
  type FeasibilityStatus,
} from "../types/synthesis-request";

interface SynthesisRequestDetailProps {
  requestId: string;
}

function statusVariant(
  s: SynthesisRequestStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (s) {
    case "fulfilled":
      return "default";
    case "approved":
    case "assigned":
    case "in_progress":
    case "synthesis_complete":
      return "secondary";
    case "rejected":
    case "cancelled":
    case "failed":
      return "destructive";
    default:
      return "outline";
  }
}

function priorityVariant(
  p: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (p) {
    case "critical":
      return "destructive";
    case "urgent":
      return "secondary";
    default:
      return "outline";
  }
}

const TERMINAL_STATUSES = new Set<SynthesisRequestStatus>([
  "fulfilled",
  "rejected",
  "cancelled",
  "failed",
]);

const CANCELLABLE_STATUSES = new Set<SynthesisRequestStatus>([
  "draft",
  "submitted",
  "approved",
  "assigned",
]);

export function SynthesisRequestDetail({
  requestId,
}: SynthesisRequestDetailProps) {
  const { data: request, isLoading } = useSynthesisRequest(requestId);

  const [rejectOpen, setRejectOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [startOpen, setStartOpen] = useState(false);
  const [flagInfeasibleOpen, setFlagInfeasibleOpen] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [fulfillOpen, setFulfillOpen] = useState(false);
  const [failOpen, setFailOpen] = useState(false);

  const submit = useSubmitSynthesisRequest();
  const approve = useApproveSynthesisRequest();
  const cancel = useCancelSynthesisRequest();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!request) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <FlaskRound className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Request not found</h3>
      </div>
    );
  }

  const isTerminal = TERMINAL_STATUSES.has(request.status);
  const isCancellable = CANCELLABLE_STATUSES.has(request.status);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/inventory/synthesis-requests">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              Synthesis Request{request.purpose ? ` \u2014 ${request.purpose.length > 40 ? request.purpose.slice(0, 40) + "\u2026" : request.purpose}` : ""}
            </h1>
            <Badge variant={statusVariant(request.status)}>
              {SYNTHESIS_REQUEST_STATUS_LABELS[request.status] ?? request.status}
            </Badge>
            <Badge variant={priorityVariant(request.priority)}>
              {request.priority
                ? request.priority.charAt(0).toUpperCase() +
                  request.priority.slice(1)
                : "\u2014"}
            </Badge>
          </div>
          <p className="mt-1 text-muted-foreground text-sm">
            Requested by <MemberName id={request.requester_id} />
          </p>
        </div>

        {/* Action buttons by status */}
        {!isTerminal && (
          <div className="flex flex-wrap gap-2">
            {/* DRAFT */}
            {request.status === "draft" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => submit.mutate(requestId)}
                disabled={submit.isPending}
              >
                {submit.isPending ? "Submitting..." : "Submit"}
              </Button>
            )}

            {/* SUBMITTED */}
            {request.status === "submitted" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => approve.mutate(requestId)}
                  disabled={approve.isPending}
                >
                  {approve.isPending ? "Approving..." : "Approve"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRejectOpen(true)}
                >
                  Reject
                </Button>
              </>
            )}

            {/* APPROVED */}
            {request.status === "approved" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAssignOpen(true)}
              >
                Assign
              </Button>
            )}

            {/* ASSIGNED */}
            {request.status === "assigned" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setStartOpen(true)}
                >
                  Start
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setFlagInfeasibleOpen(true)}
                >
                  Flag Infeasible
                </Button>
              </>
            )}

            {/* IN_PROGRESS */}
            {request.status === "in_progress" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCompleteOpen(true)}
                >
                  Complete
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setFailOpen(true)}
                >
                  Fail
                </Button>
              </>
            )}

            {/* SYNTHESIS_COMPLETE */}
            {request.status === "synthesis_complete" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFulfillOpen(true)}
              >
                Fulfill
              </Button>
            )}

            {/* Cancel (available for draft/submitted/approved/assigned) */}
            {isCancellable && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => cancel.mutate(requestId)}
                disabled={cancel.isPending}
              >
                {cancel.isPending ? "Cancelling..." : "Cancel"}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Request Details */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Request Details</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Compound</p>
            <p className="font-medium text-sm">
              <MoleculeName id={request.molecule_id} />
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Amount</p>
            <p className="font-medium">
              {request.amount_value} {request.amount_unit}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Priority</p>
            <p className="font-medium">
              {request.priority
                ? request.priority.charAt(0).toUpperCase() +
                  request.priority.slice(1)
                : "\u2014"}
            </p>
          </div>
          {request.target_purity != null && (
            <div>
              <p className="text-xs text-muted-foreground">Target Purity</p>
              <p className="font-medium">{request.target_purity}%</p>
            </div>
          )}
          {request.parent_request_id && (
            <div>
              <p className="text-xs text-muted-foreground">Follow-up of</p>
              <a href={`/inventory/synthesis-requests/${request.parent_request_id}`} className="text-sm text-primary hover:underline">
                View parent request
              </a>
            </div>
          )}
        </div>
        <div className="mt-4">
          <p className="text-xs text-muted-foreground">Purpose</p>
          <p className="mt-1 text-sm">{request.purpose}</p>
        </div>
      </Card>

      {/* Status & Timeline */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Status &amp; Timeline</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Status</p>
            <Badge variant={statusVariant(request.status)} className="mt-1">
              {SYNTHESIS_REQUEST_STATUS_LABELS[request.status] ?? request.status}
            </Badge>
          </div>
          {request.approved_by && (
            <div>
              <p className="text-xs text-muted-foreground">Approved By</p>
              <p className="font-medium text-sm">
                <MemberName id={request.approved_by} />
              </p>
            </div>
          )}
          {request.approved_at && (
            <div>
              <p className="text-xs text-muted-foreground">Approved At</p>
              <p className="font-medium text-sm">
                {new Date(request.approved_at).toLocaleString()}
              </p>
            </div>
          )}
          {request.estimated_completion_date && (
            <div>
              <p className="text-xs text-muted-foreground">
                Est. Completion
              </p>
              <p className="font-medium text-sm">
                {new Date(request.estimated_completion_date).toLocaleDateString()}
              </p>
            </div>
          )}
          {request.actual_completion_date && (
            <div>
              <p className="text-xs text-muted-foreground">
                Actual Completion
              </p>
              <p className="font-medium text-sm">
                {new Date(request.actual_completion_date).toLocaleDateString()}
              </p>
            </div>
          )}
        </div>
      </Card>

      {/* Assignment */}
      {(request.assignment_type ||
        request.assigned_to ||
        request.assigned_org_id ||
        request.proposed_route_id) && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Assignment</h2>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            {request.assignment_type && (
              <div>
                <p className="text-xs text-muted-foreground">Assignment Type</p>
                <p className="font-medium capitalize">
                  {request.assignment_type}
                </p>
              </div>
            )}
            {request.assigned_to && (
              <div>
                <p className="text-xs text-muted-foreground">Assigned To</p>
                <p className="font-medium text-sm">
                  <MemberName id={request.assigned_to} />
                </p>
              </div>
            )}
            {request.assigned_org_id && (
              <div>
                <p className="text-xs text-muted-foreground">Assigned Org</p>
                <p className="font-medium text-sm">
                  <OrgName id={request.assigned_org_id} />
                </p>
              </div>
            )}
            {request.proposed_route_id && (
              <div>
                <p className="text-xs text-muted-foreground">Proposed Route</p>
                <p className="font-medium text-sm">
                  <RouteName id={request.proposed_route_id} />
                </p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Feasibility */}
      {(request.feasibility_status || request.feasibility_notes) && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Feasibility</h2>
          <div className="mt-4 grid grid-cols-2 gap-4">
            {request.feasibility_status && (
              <div>
                <p className="text-xs text-muted-foreground">
                  Feasibility Status
                </p>
                <p className="font-medium">
                  {FEASIBILITY_STATUS_LABELS[request.feasibility_status] ??
                    request.feasibility_status}
                </p>
              </div>
            )}
          </div>
          {request.feasibility_notes && (
            <div className="mt-4">
              <p className="text-xs text-muted-foreground">Notes</p>
              <p className="mt-1 text-sm">{request.feasibility_notes}</p>
            </div>
          )}
        </Card>
      )}

      {/* Cost */}
      {(request.estimated_cost_value != null ||
        request.actual_cost_value != null) && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Cost</h2>
          <div className="mt-4 grid grid-cols-2 gap-4">
            {request.estimated_cost_value != null && (
              <div>
                <p className="text-xs text-muted-foreground">Estimated Cost</p>
                <p className="font-medium">
                  {request.estimated_cost_value}{" "}
                  {request.estimated_cost_unit ?? ""}
                </p>
              </div>
            )}
            {request.actual_cost_value != null && (
              <div>
                <p className="text-xs text-muted-foreground">Actual Cost</p>
                <p className="font-medium">
                  {request.actual_cost_value}{" "}
                  {request.actual_cost_unit ?? ""}
                </p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Completion / Terminal */}
      {(request.fulfilled_batch_id || request.rejection_reason || request.failure_reason) && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Completion</h2>
          <div className="mt-4 grid grid-cols-2 gap-4">
            {request.fulfilled_batch_id && (
              <div>
                <p className="text-xs text-muted-foreground">Fulfilled Batch</p>
                <p className="font-medium text-sm">
                  <BatchName id={request.fulfilled_batch_id} />
                </p>
              </div>
            )}
          </div>
          {request.rejection_reason && (
            <div className="mt-4">
              <p className="text-xs text-muted-foreground">Rejection Reason</p>
              <p className="mt-1 text-sm text-destructive">
                {request.rejection_reason}
              </p>
            </div>
          )}
          {request.failure_reason && (
            <div className="mt-4">
              <p className="text-xs text-muted-foreground">Failure Reason</p>
              <p className="mt-1 text-sm text-destructive">
                {request.failure_reason}
              </p>
            </div>
          )}
        </Card>
      )}

      {/* Action dialogs */}
      <RejectDialog
        request={request}
        open={rejectOpen}
        onOpenChange={setRejectOpen}
      />
      <AssignDialog
        request={request}
        open={assignOpen}
        onOpenChange={setAssignOpen}
      />
      <StartDialog
        request={request}
        open={startOpen}
        onOpenChange={setStartOpen}
      />
      <FlagInfeasibleDialog
        request={request}
        open={flagInfeasibleOpen}
        onOpenChange={setFlagInfeasibleOpen}
      />
      <CompleteDialog
        request={request}
        open={completeOpen}
        onOpenChange={setCompleteOpen}
      />
      <FulfillDialog
        request={request}
        open={fulfillOpen}
        onOpenChange={setFulfillOpen}
      />
      <FailDialog
        request={request}
        open={failOpen}
        onOpenChange={setFailOpen}
      />
    </div>
  );
}

// --- Inline action dialogs ---

function RejectDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useRejectSynthesisRequest();
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
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
              mutation.mutate(
                { id: request.id, reason },
                { onSuccess: () => onOpenChange(false) }
              );
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

function AssignDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useAssignSynthesisRequest();
  const [assignmentType, setAssignmentType] = useState("internal");
  const [assignedToId, setAssignedToId] = useState<string | null>(null);
  const [assignedOrgId, setAssignedOrgId] = useState("");

  const { data: organizations, isLoading: orgsLoading } = useOrganizations();

  const isValid =
    (assignmentType === "internal" && assignedToId !== null) ||
    (assignmentType === "cro" && assignedOrgId.trim() !== "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Assign Request</DialogTitle>
          <DialogDescription>
            Assign this synthesis request to a chemist or CRO.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Assignment Type</Label>
            <Select value={assignmentType} onValueChange={(v) => { setAssignmentType(v); setAssignedToId(null); setAssignedOrgId(""); }}>
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
              <Select
                value={assignedOrgId}
                onValueChange={setAssignedOrgId}
                disabled={orgsLoading}
              >
                <SelectTrigger id="assign-org">
                  <SelectValue
                    placeholder={
                      orgsLoading ? "Loading organizations..." : "Select CRO..."
                    }
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
                  assigned_to:
                    assignmentType === "internal" ? assignedToId : null,
                  assigned_org_id:
                    assignmentType === "cro" && assignedOrgId.trim()
                      ? assignedOrgId.trim()
                      : null,
                },
                { onSuccess: () => onOpenChange(false) }
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

function StartDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useStartSynthesis();
  const [proposedRouteId, setProposedRouteId] = useState("");

  const { data: routes, isLoading: routesLoading } =
    useSynthesisRoutesByMolecule(request.molecule_id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Start Synthesis</DialogTitle>
          <DialogDescription>
            Begin synthesis. Optionally link a proposed synthesis route.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label htmlFor="start-route">Proposed Route (optional)</Label>
          <Select
            value={proposedRouteId}
            onValueChange={setProposedRouteId}
            disabled={routesLoading}
          >
            <SelectTrigger id="start-route">
              <SelectValue
                placeholder={
                  routesLoading ? "Loading routes..." : "None — start without a route"
                }
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
          {!routesLoading && (!routes || routes.length === 0) && (
            <p className="text-xs text-muted-foreground">
              No synthesis routes found for this molecule. You can start without
              one.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  proposed_route_id: proposedRouteId && proposedRouteId !== "none" ? proposedRouteId : null,
                },
                { onSuccess: () => onOpenChange(false) }
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

function FlagInfeasibleDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useFlagInfeasible();
  const [feasibilityStatus, setFeasibilityStatus] =
    useState<FeasibilityStatus>("infeasible");
  const [notes, setNotes] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
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
              onValueChange={(v) =>
                setFeasibilityStatus(v as FeasibilityStatus)
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(FEASIBILITY_STATUS_LABELS).map(
                  ([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  )
                )}
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
                { onSuccess: () => onOpenChange(false) }
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

function CompleteDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useCompleteSynthesis();
  const [actualCostValue, setActualCostValue] = useState("");
  const [actualCostUnit, setActualCostUnit] = useState("USD");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
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
                    actualCostValue !== ""
                      ? parseFloat(actualCostValue)
                      : null,
                  actual_cost_unit:
                    actualCostValue !== "" ? actualCostUnit : null,
                },
                { onSuccess: () => onOpenChange(false) }
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

function FulfillDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useFulfillSynthesisRequest();
  const [batchId, setBatchId] = useState("");

  const { data: batches, isLoading: batchesLoading } = useBatchesByMolecule(
    request.molecule_id
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Fulfill Request</DialogTitle>
          <DialogDescription>
            Select the synthesized batch to fulfill this request.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label htmlFor="fulfill-batch">Batch</Label>
          <Select
            value={batchId}
            onValueChange={setBatchId}
            disabled={batchesLoading}
          >
            <SelectTrigger id="fulfill-batch">
              <SelectValue
                placeholder={
                  batchesLoading ? "Loading batches..." : "Select batch..."
                }
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
              No batches found for this molecule. Register the synthesized batch
              first.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { id: request.id, batch_id: batchId },
                { onSuccess: () => onOpenChange(false) }
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

function FailDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SynthesisRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useFailSynthesis();
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Mark as Failed</DialogTitle>
          <DialogDescription>
            Record the reason for synthesis failure.
          </DialogDescription>
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
              mutation.mutate(
                { id: request.id, reason },
                { onSuccess: () => onOpenChange(false) }
              );
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
