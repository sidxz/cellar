"use client";

import { DetailShell } from "@/shared/components/detail-shell";
import { BatchName, MemberName, MoleculeName, SampleName } from "@/shared/components/entity-name";
import { PriorityBadge } from "@/shared/components/status-badge";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { formatDateTime } from "@/shared/lib/format-date";
import { useAuthz } from "@sentinel-auth/nextjs";
import { Pencil } from "lucide-react";
import { useState } from "react";
import {
  useApproveSampleRequest,
  useCancelSampleRequest,
  useFulfillSampleRequest,
  useRejectSampleRequest,
  useSampleRequest,
  useStartPreparingSampleRequest,
  useUpdateSampleRequest,
} from "../hooks/use-sample-requests";
import { useSamplesByBatch } from "../hooks/use-samples";
import {
  REQUEST_PRIORITY_LABELS,
  type RequestPriority,
  SAMPLE_REQUEST_STATUS_LABELS,
  type SampleRequest,
  type SampleRequestStatus,
} from "../types/sample-request";

interface SampleRequestDetailProps {
  requestId: string;
}

const TERMINAL_STATUSES = new Set<SampleRequestStatus>(["fulfilled", "rejected", "cancelled"]);

export function SampleRequestDetail({ requestId }: SampleRequestDetailProps) {
  const query = useSampleRequest(requestId);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [fulfillOpen, setFulfillOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const startPreparing = useStartPreparingSampleRequest();
  const cancel = useCancelSampleRequest();

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/sample-requests"
        backLabel="Back to Sample Requests"
        title={(r) =>
          `Sample Request${r.purpose ? ` \u2014 ${r.purpose.length > 40 ? `${r.purpose.slice(0, 40)}\u2026` : r.purpose}` : ""}`
        }
        badge={(r) => ({
          status: r.status,
          label: SAMPLE_REQUEST_STATUS_LABELS[r.status as SampleRequestStatus] ?? r.status,
        })}
        notFoundMessage="Request not found."
        actions={(r) => {
          const isTerminal = TERMINAL_STATUSES.has(r.status as SampleRequestStatus);
          if (isTerminal) return undefined;
          return (
            <>
              {r.status === "submitted" && (
                <>
                  <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                    <Pencil className="mr-1 h-3.5 w-3.5" />
                    Edit
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setApproveOpen(true)}>
                    Approve
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setRejectOpen(true)}>
                    Reject
                  </Button>
                </>
              )}
              {r.status === "approved" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startPreparing.mutate({ id: requestId })}
                  disabled={startPreparing.isPending}
                >
                  {startPreparing.isPending ? "Starting..." : "Start Preparing"}
                </Button>
              )}
              {r.status === "preparing" && (
                <Button variant="outline" size="sm" onClick={() => setFulfillOpen(true)}>
                  Fulfill
                </Button>
              )}
              {(r.status === "submitted" ||
                r.status === "approved" ||
                r.status === "preparing") && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => cancel.mutate({ id: requestId })}
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
              <PriorityBadge
                priority={request.priority}
                label={
                  REQUEST_PRIORITY_LABELS[request.priority as RequestPriority] ?? request.priority
                }
              />
              <span className="text-muted-foreground text-sm">
                Requested by <MemberName id={request.requester_id} />
              </span>
            </div>

            {/* Details card */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold">Request Details</h2>
              <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div>
                  <p className="text-xs text-muted-foreground">Compound</p>
                  <p className="font-medium text-sm">
                    <MoleculeName id={request.molecule_id} />
                  </p>
                </div>
                {request.batch_id && (
                  <div>
                    <p className="text-xs text-muted-foreground">Preferred Batch</p>
                    <p className="font-medium text-sm">
                      <BatchName id={request.batch_id} />
                    </p>
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
                    {REQUEST_PRIORITY_LABELS[request.priority as RequestPriority] ??
                      request.priority}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Status</p>
                  <p className="font-medium">
                    {SAMPLE_REQUEST_STATUS_LABELS[request.status as SampleRequestStatus] ??
                      request.status}
                  </p>
                </div>
                {request.assigned_to && (
                  <div>
                    <p className="text-xs text-muted-foreground">Assigned To</p>
                    <p className="font-medium text-sm">
                      <MemberName id={request.assigned_to} />
                    </p>
                  </div>
                )}
                {request.fulfilled_sample_id && (
                  <div>
                    <p className="text-xs text-muted-foreground">Fulfilled Sample</p>
                    <p className="font-medium text-sm">
                      <SampleName id={request.fulfilled_sample_id} />
                    </p>
                  </div>
                )}
                {request.fulfilled_at && (
                  <div>
                    <p className="text-xs text-muted-foreground">Fulfilled At</p>
                    <p className="font-medium">{formatDateTime(request.fulfilled_at)}</p>
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
                  <p className="mt-1 text-sm text-destructive">{request.rejection_reason}</p>
                </div>
              )}
            </Card>
          </>
        )}
      </DetailShell>

      {/* Action dialogs */}
      {query.data?.status === "submitted" && (
        <EditSampleRequestDialog request={query.data} open={editOpen} onOpenChange={setEditOpen} />
      )}
      {query.data && (
        <>
          <ApproveDialog request={query.data} open={approveOpen} onOpenChange={setApproveOpen} />
          <RejectDialog request={query.data} open={rejectOpen} onOpenChange={setRejectOpen} />
          <FulfillDialog request={query.data} open={fulfillOpen} onOpenChange={setFulfillOpen} />
        </>
      )}
    </>
  );
}

// --- Inline action dialogs ---

function EditSampleRequestDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SampleRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdateSampleRequest();
  const [purpose, setPurpose] = useState(request.purpose);
  const [priority, setPriority] = useState<string>(request.priority);
  const [amountValue, setAmountValue] = useState(String(request.amount_value));
  const [amountUnit, setAmountUnit] = useState(request.amount_unit);

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setPurpose(request.purpose);
          setPriority(request.priority);
          setAmountValue(String(request.amount_value));
          setAmountUnit(request.amount_unit);
        }
        onOpenChange(v);
      }}
    >
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Edit Sample Request</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="edit-sr-purpose">Purpose</Label>
            <Textarea
              id="edit-sr-purpose"
              rows={3}
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-sr-priority">Priority</Label>
            <Select value={priority} onValueChange={setPriority}>
              <SelectTrigger id="edit-sr-priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(REQUEST_PRIORITY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="edit-sr-amount">Amount</Label>
              <Input
                id="edit-sr-amount"
                type="number"
                min={0}
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-sr-unit">Unit</Label>
              <select
                id="edit-sr-unit"
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
  const { user } = useAuthz();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Approve Request</DialogTitle>
          <DialogDescription>
            Approve this sample request and assign it to yourself.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <div className="rounded-md border border-border bg-muted/50 p-3">
            <p className="text-sm text-muted-foreground">
              Will be assigned to you ({user?.name ?? user?.email ?? "current user"})
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: request.id,
                  assigned_to: user?.userId ?? undefined,
                },
                { onSuccess: () => onOpenChange(false) },
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
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Reject Request</DialogTitle>
          <DialogDescription>Provide a reason for rejecting this request.</DialogDescription>
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

  // If the request targets a specific batch, offer a select of known samples.
  const { data: batchSamples, isLoading: samplesLoading } = useSamplesByBatch(
    request.batch_id ?? undefined,
  );
  const hasBatchSamples = !!request.batch_id && batchSamples && batchSamples.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Fulfill Request</DialogTitle>
          <DialogDescription>Link the dispensed sample to this request.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          {hasBatchSamples ? (
            <>
              <Label htmlFor="fulfill-sample">Sample</Label>
              <Select value={sampleId} onValueChange={setSampleId}>
                <SelectTrigger id="fulfill-sample">
                  <SelectValue placeholder="Select sample..." />
                </SelectTrigger>
                <SelectContent>
                  {batchSamples.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.barcode}
                      {s.amount_value != null ? ` — ${s.amount_value} ${s.amount_unit}` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          ) : (
            <>
              <Label htmlFor="fulfill-sample">Sample Barcode</Label>
              <Input
                id="fulfill-sample"
                placeholder={samplesLoading ? "Loading samples..." : "e.g. SMP-0042"}
                value={sampleId}
                onChange={(e) => setSampleId(e.target.value)}
                disabled={samplesLoading}
              />
              <p className="text-xs text-muted-foreground">
                Enter the barcode of the sample being dispensed.
              </p>
            </>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { id: request.id, sample_id: sampleId },
                { onSuccess: () => onOpenChange(false) },
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
