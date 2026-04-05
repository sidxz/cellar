"use client";

import { useState } from "react";
import { ArrowLeft, ClipboardList } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/shared/components/ui/badge";
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
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  useSampleRequest,
  useApproveSampleRequest,
  useRejectSampleRequest,
  useStartPreparingSampleRequest,
  useFulfillSampleRequest,
  useCancelSampleRequest,
} from "../hooks/use-sample-requests";
import {
  SAMPLE_REQUEST_STATUS_LABELS,
  REQUEST_PRIORITY_LABELS,
  type SampleRequest,
  type SampleRequestStatus,
  type RequestPriority,
} from "../types/sample-request";

interface SampleRequestDetailProps {
  requestId: string;
}

function statusVariant(
  s: SampleRequestStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (s) {
    case "fulfilled":
      return "default";
    case "approved":
    case "preparing":
      return "secondary";
    case "rejected":
    case "cancelled":
      return "destructive";
    default:
      return "outline";
  }
}

function priorityVariant(
  p: RequestPriority
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

const TERMINAL_STATUSES = new Set<SampleRequestStatus>([
  "fulfilled",
  "rejected",
  "cancelled",
]);

export function SampleRequestDetail({ requestId }: SampleRequestDetailProps) {
  const { data: request, isLoading } = useSampleRequest(requestId);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [fulfillOpen, setFulfillOpen] = useState(false);

  const startPreparing = useStartPreparingSampleRequest();
  const cancel = useCancelSampleRequest();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!request) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <ClipboardList className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Request not found</h3>
      </div>
    );
  }

  const isTerminal = TERMINAL_STATUSES.has(request.status);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/inventory/sample-requests">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              {request.id.slice(0, 8)}&hellip;
            </h1>
            <Badge variant={statusVariant(request.status)}>
              {SAMPLE_REQUEST_STATUS_LABELS[request.status] ?? request.status}
            </Badge>
            <Badge variant={priorityVariant(request.priority)}>
              {REQUEST_PRIORITY_LABELS[request.priority] ?? request.priority}
            </Badge>
          </div>
          <p className="mt-1 text-muted-foreground text-sm">
            Requested by {request.requester_id.slice(0, 8)}&hellip;
          </p>
        </div>

        {/* Action buttons by status */}
        {!isTerminal && (
          <div className="flex gap-2">
            {request.status === "submitted" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setApproveOpen(true)}
                >
                  Approve
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
            {request.status === "approved" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  startPreparing.mutate({ id: requestId })
                }
                disabled={startPreparing.isPending}
              >
                {startPreparing.isPending ? "Starting..." : "Start Preparing"}
              </Button>
            )}
            {request.status === "preparing" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFulfillOpen(true)}
              >
                Fulfill
              </Button>
            )}
            {(request.status === "submitted" ||
              request.status === "approved" ||
              request.status === "preparing") && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => cancel.mutate({ id: requestId })}
                disabled={cancel.isPending}
              >
                {cancel.isPending ? "Cancelling..." : "Cancel"}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Details card */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Request Details</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Molecule ID</p>
            <p className="font-mono text-sm break-all">{request.molecule_id}</p>
          </div>
          {request.batch_id && (
            <div>
              <p className="text-xs text-muted-foreground">Batch ID</p>
              <p className="font-mono text-sm break-all">{request.batch_id}</p>
            </div>
          )}
          <div>
            <p className="text-xs text-muted-foreground">Amount</p>
            <p className="font-medium">
              {request.amount_value} {request.amount_unit}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Priority</p>
            <p className="font-medium">
              {REQUEST_PRIORITY_LABELS[request.priority] ?? request.priority}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Status</p>
            <p className="font-medium">
              {SAMPLE_REQUEST_STATUS_LABELS[request.status] ?? request.status}
            </p>
          </div>
          {request.assigned_to && (
            <div>
              <p className="text-xs text-muted-foreground">Assigned To</p>
              <p className="font-mono text-sm">{request.assigned_to.slice(0, 8)}&hellip;</p>
            </div>
          )}
          {request.fulfilled_sample_id && (
            <div>
              <p className="text-xs text-muted-foreground">Fulfilled Sample ID</p>
              <p className="font-mono text-sm break-all">
                {request.fulfilled_sample_id}
              </p>
            </div>
          )}
          {request.fulfilled_at && (
            <div>
              <p className="text-xs text-muted-foreground">Fulfilled At</p>
              <p className="font-medium">
                {new Date(request.fulfilled_at).toLocaleString()}
              </p>
            </div>
          )}
        </div>
        <div className="mt-4">
          <p className="text-xs text-muted-foreground">Purpose</p>
          <p className="mt-1 text-sm">{request.purpose}</p>
        </div>
        {request.rejection_reason && (
          <div className="mt-4">
            <p className="text-xs text-muted-foreground">Rejection Reason</p>
            <p className="mt-1 text-sm text-destructive">
              {request.rejection_reason}
            </p>
          </div>
        )}
      </Card>

      {/* Action dialogs */}
      <ApproveDialog
        request={request}
        open={approveOpen}
        onOpenChange={setApproveOpen}
      />
      <RejectDialog
        request={request}
        open={rejectOpen}
        onOpenChange={setRejectOpen}
      />
      <FulfillDialog
        request={request}
        open={fulfillOpen}
        onOpenChange={setFulfillOpen}
      />
    </div>
  );
}

// --- Inline action dialogs ---

function ApproveDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SampleRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useApproveSampleRequest();
  const [assignedTo, setAssignedTo] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Approve Request</DialogTitle>
          <DialogDescription>
            Approve this sample request. Optionally assign it to a user.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Assign To (optional — user ID)</Label>
          <Input
            placeholder="User UUID"
            value={assignedTo}
            onChange={(e) => setAssignedTo(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  assigned_to: assignedTo || undefined,
                },
                { onSuccess: () => onOpenChange(false) }
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Approving..." : "Approve"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SampleRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useRejectSampleRequest();
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Reject Request</DialogTitle>
          <DialogDescription>
            Provide a reason for rejecting this request.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Reason</Label>
          <Input
            placeholder="e.g., insufficient stock"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
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

function FulfillDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SampleRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useFulfillSampleRequest();
  const [sampleId, setSampleId] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Fulfill Request</DialogTitle>
          <DialogDescription>
            Link the fulfilled sample to this request.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Sample ID</Label>
          <Input
            placeholder="UUID of the dispensed sample"
            value={sampleId}
            onChange={(e) => setSampleId(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { id: request.id, sample_id: sampleId },
                { onSuccess: () => onOpenChange(false) }
              );
            }}
            disabled={!sampleId.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Fulfilling..." : "Fulfill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
