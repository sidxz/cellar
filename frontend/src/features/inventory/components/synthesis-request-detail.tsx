"use client";

import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import {
  BatchName,
  MemberName,
  MoleculeName,
  OrgName,
  RouteName,
} from "@/shared/components/entity-name";
import { PriorityBadge, StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { formatDate, formatDateTime } from "@/shared/lib/format-date";
import { Pencil, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useSynthesisRequestActions } from "../hooks/use-synthesis-request-actions";
import { useSynthesisRequest } from "../hooks/use-synthesis-requests";
import {
  FEASIBILITY_STATUS_LABELS,
  SYNTHESIS_REQUEST_STATUS_LABELS,
  type SynthesisRequestStatus,
} from "../types/synthesis-request";
import {
  AssignDialog,
  CompleteDialog,
  EditSynthesisRequestDialog,
  FailDialog,
  FlagInfeasibleDialog,
  FulfillDialog,
  RejectDialog,
  StartDialog,
} from "./synthesis-request-dialogs";

interface SynthesisRequestDetailProps {
  requestId: string;
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

export function SynthesisRequestDetail({ requestId }: SynthesisRequestDetailProps) {
  const router = useRouter();
  const query = useSynthesisRequest(requestId);

  const { activeDialog, openDialog, closeDialog, mutations } = useSynthesisRequestActions();
  const {
    submit,
    approve,
    cancel,
    deleteMutation,
    reject,
    assign,
    start,
    flagInfeasible,
    complete,
    fulfill,
    fail,
    update,
  } = mutations;

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/synthesis-requests"
        backLabel="Back to Synthesis Requests"
        title={(r) =>
          `Synthesis Request${r.purpose ? ` \u2014 ${r.purpose.length > 40 ? `${r.purpose.slice(0, 40)}\u2026` : r.purpose}` : ""}`
        }
        badge={(r) => ({
          status: r.status,
          label: SYNTHESIS_REQUEST_STATUS_LABELS[r.status] ?? r.status,
        })}
        notFoundMessage="Request not found."
        actions={(r) => {
          const isTerminal = TERMINAL_STATUSES.has(r.status);
          const isCancellable = CANCELLABLE_STATUSES.has(r.status);
          if (isTerminal) return undefined;
          return (
            <>
              {r.status === "draft" && (
                <>
                  <Button variant="outline" size="sm" onClick={() => openDialog("edit")}>
                    <Pencil className="mr-1 h-3.5 w-3.5" />
                    Edit
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => submit.mutate(requestId)}
                    disabled={submit.isPending}
                  >
                    {submit.isPending ? "Submitting..." : "Submit"}
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => openDialog("delete")}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                    Delete
                  </Button>
                </>
              )}
              {r.status === "submitted" && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => approve.mutate(requestId)}
                    disabled={approve.isPending}
                  >
                    {approve.isPending ? "Approving..." : "Approve"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => openDialog("reject")}>
                    Reject
                  </Button>
                </>
              )}
              {r.status === "approved" && (
                <Button variant="outline" size="sm" onClick={() => openDialog("assign")}>
                  Assign
                </Button>
              )}
              {r.status === "assigned" && (
                <>
                  <Button variant="outline" size="sm" onClick={() => openDialog("start")}>
                    Start
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => openDialog("flagInfeasible")}>
                    Flag Infeasible
                  </Button>
                </>
              )}
              {r.status === "in_progress" && (
                <>
                  <Button variant="outline" size="sm" onClick={() => openDialog("complete")}>
                    Complete
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => openDialog("fail")}>
                    Fail
                  </Button>
                </>
              )}
              {r.status === "synthesis_complete" && (
                <Button variant="outline" size="sm" onClick={() => openDialog("fulfill")}>
                  Fulfill
                </Button>
              )}
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
            </>
          );
        }}
      >
        {(request) => (
          <>
            <div className="-mt-3 flex items-center gap-2">
              <PriorityBadge priority={request.priority ?? ""} />
              <span className="text-muted-foreground text-sm">
                Requested by <MemberName id={request.requester_id} />
              </span>
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
                      ? request.priority.charAt(0).toUpperCase() + request.priority.slice(1)
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
                    <a
                      href={`/inventory/synthesis-requests/${request.parent_request_id}`}
                      className="text-sm text-primary hover:underline"
                    >
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
                  <StatusBadge
                    status={request.status}
                    label={SYNTHESIS_REQUEST_STATUS_LABELS[request.status] ?? request.status}
                    className="mt-1"
                  />
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
                    <p className="font-medium text-sm">{formatDateTime(request.approved_at)}</p>
                  </div>
                )}
                {request.estimated_completion_date && (
                  <div>
                    <p className="text-xs text-muted-foreground">Est. Completion</p>
                    <p className="font-medium text-sm">
                      {formatDate(request.estimated_completion_date)}
                    </p>
                  </div>
                )}
                {request.actual_completion_date && (
                  <div>
                    <p className="text-xs text-muted-foreground">Actual Completion</p>
                    <p className="font-medium text-sm">
                      {formatDate(request.actual_completion_date)}
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
                      <p className="font-medium capitalize">{request.assignment_type}</p>
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
                      <p className="text-xs text-muted-foreground">Feasibility Status</p>
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
            {(request.estimated_cost_value != null || request.actual_cost_value != null) && (
              <Card className="p-6">
                <h2 className="text-lg font-semibold">Cost</h2>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  {request.estimated_cost_value != null && (
                    <div>
                      <p className="text-xs text-muted-foreground">Estimated Cost</p>
                      <p className="font-medium">
                        {request.estimated_cost_value} {request.estimated_cost_unit ?? ""}
                      </p>
                    </div>
                  )}
                  {request.actual_cost_value != null && (
                    <div>
                      <p className="text-xs text-muted-foreground">Actual Cost</p>
                      <p className="font-medium">
                        {request.actual_cost_value} {request.actual_cost_unit ?? ""}
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
                    <p className="mt-1 text-sm text-destructive">{request.rejection_reason}</p>
                  </div>
                )}
                {request.failure_reason && (
                  <div className="mt-4">
                    <p className="text-xs text-muted-foreground">Failure Reason</p>
                    <p className="mt-1 text-sm text-destructive">{request.failure_reason}</p>
                  </div>
                )}
              </Card>
            )}
          </>
        )}
      </DetailShell>

      {/* Action dialogs */}
      {query.data?.status === "draft" && (
        <EditSynthesisRequestDialog
          request={query.data}
          open={activeDialog === "edit"}
          onOpenChange={(v) => {
            if (!v) closeDialog();
          }}
          mutation={update}
        />
      )}
      {query.data && (
        <>
          <RejectDialog
            request={query.data}
            open={activeDialog === "reject"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={reject}
          />
          <AssignDialog
            request={query.data}
            open={activeDialog === "assign"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={assign}
          />
          <StartDialog
            request={query.data}
            open={activeDialog === "start"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={start}
          />
          <FlagInfeasibleDialog
            request={query.data}
            open={activeDialog === "flagInfeasible"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={flagInfeasible}
          />
          <CompleteDialog
            request={query.data}
            open={activeDialog === "complete"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={complete}
          />
          <FulfillDialog
            request={query.data}
            open={activeDialog === "fulfill"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={fulfill}
          />
          <FailDialog
            request={query.data}
            open={activeDialog === "fail"}
            onOpenChange={(v) => {
              if (!v) closeDialog();
            }}
            mutation={fail}
          />
        </>
      )}

      <ConfirmDeleteDialog
        open={activeDialog === "delete"}
        onOpenChange={(v) => {
          if (!v) closeDialog();
        }}
        title="Delete Synthesis Request"
        description="This will permanently delete this synthesis request. This action cannot be undone."
        onConfirm={() =>
          deleteMutation.mutate(requestId, {
            onSuccess: () => router.push("/inventory/synthesis-requests"),
          })
        }
        isPending={deleteMutation.isPending}
      />
    </>
  );
}
