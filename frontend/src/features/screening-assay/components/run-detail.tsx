"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Play,
  CheckCircle2,
  ThumbsUp,
  ThumbsDown,
  Lock,
  Paperclip,
  Unlock,
} from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
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
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Textarea } from "@/shared/components/ui/textarea";
import { EntityLink } from "@/shared/components/entity-link";
import { FileUploadZone, AttachmentList } from "@/features/attachment";
import {
  useRun,
  useStartRun,
  useCompleteRun,
  useApproveRun,
  useRejectRun,
  useLockRun,
  useUnlockRun,
} from "../hooks/use-runs";
import {
  PLATE_FORMAT_LABELS,
  type PlateFormat,
  type RunStatus,
} from "../types";
import { RunDataPanel } from "./run-data-panel";

interface RunDetailProps {
  runId: string;
}

function statusBadgeVariant(
  status: RunStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "approved":
      return "default";
    case "completed":
    case "in_progress":
      return "secondary";
    case "rejected":
      return "destructive";
    case "draft":
      return "outline";
  }
}

export function RunDetail({ runId }: RunDetailProps) {
  const router = useRouter();
  const { data: run, isLoading } = useRun(runId);
  const startMutation = useStartRun();
  const completeMutation = useCompleteRun();
  const approveMutation = useApproveRun();
  const rejectMutation = useRejectRun();
  const lockMutation = useLockRun();
  const unlockMutation = useUnlockRun();

  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [lockDialogOpen, setLockDialogOpen] = useState(false);
  const [lockReason, setLockReason] = useState("");
  const [unlockDialogOpen, setUnlockDialogOpen] = useState(false);
  const [unlockReason, setUnlockReason] = useState("");

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="text-center text-muted-foreground py-12">
        Run not found.
      </div>
    );
  }

  const status = run.status as RunStatus;

  const handleReject = () => {
    rejectMutation.mutate(
      { id: runId, reason: rejectReason },
      {
        onSuccess: () => {
          setRejectDialogOpen(false);
          setRejectReason("");
        },
      }
    );
  };

  const handleLock = () => {
    lockMutation.mutate(
      { id: runId, reason: lockReason },
      {
        onSuccess: () => {
          setLockDialogOpen(false);
          setLockReason("");
        },
      }
    );
  };

  const handleUnlock = () => {
    unlockMutation.mutate(
      { id: runId, reason: unlockReason },
      {
        onSuccess: () => {
          setUnlockDialogOpen(false);
          setUnlockReason("");
        },
      }
    );
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.back()}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">
            Run {run.run_date}
          </h1>
          <Badge variant={statusBadgeVariant(status)}>{status}</Badge>
          <Badge variant={run.is_locked ? "destructive" : "outline"}>
            {run.is_locked ? (
              <>
                <Lock className="mr-1 h-3 w-3" />
                Locked
              </>
            ) : (
              <>
                <Unlock className="mr-1 h-3 w-3" />
                Unlocked
              </>
            )}
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          {/* Lifecycle buttons */}
          {status === "draft" && (
            <Button
              size="sm"
              onClick={() => startMutation.mutate(runId)}
              disabled={startMutation.isPending}
            >
              <Play className="mr-2 h-4 w-4" />
              {startMutation.isPending ? "Starting..." : "Start"}
            </Button>
          )}
          {status === "in_progress" && (
            <Button
              size="sm"
              onClick={() =>
                completeMutation.mutate({
                  id: runId,
                  plate_count: run.plate_count,
                  data_point_count: 0,
                })
              }
              disabled={completeMutation.isPending}
            >
              <CheckCircle2 className="mr-2 h-4 w-4" />
              {completeMutation.isPending ? "Completing..." : "Complete"}
            </Button>
          )}
          {status === "completed" && (
            <>
              <Button
                size="sm"
                onClick={() => approveMutation.mutate(runId)}
                disabled={approveMutation.isPending}
              >
                <ThumbsUp className="mr-2 h-4 w-4" />
                {approveMutation.isPending ? "Approving..." : "Approve"}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setRejectDialogOpen(true)}
              >
                <ThumbsDown className="mr-2 h-4 w-4" />
                Reject
              </Button>
            </>
          )}

          {/* Lock / Unlock */}
          {status !== "draft" && !run.is_locked && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setLockDialogOpen(true)}
            >
              <Lock className="mr-2 h-4 w-4" />
              Lock
            </Button>
          )}
          {status !== "draft" && run.is_locked && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setUnlockDialogOpen(true)}
            >
              <Unlock className="mr-2 h-4 w-4" />
              Unlock
            </Button>
          )}
        </div>
      </div>

      {/* Metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground">Protocol</p>
              <EntityLink
                type="protocol"
                id={run.protocol_id}
                label={run.protocol_id.slice(0, 8)}
              />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Run Date</p>
              <p className="font-medium font-mono">{run.run_date}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Plate Format</p>
              <p className="font-medium">
                {run.plate_format
                  ? PLATE_FORMAT_LABELS[run.plate_format as PlateFormat] ??
                    run.plate_format
                  : "\u2014"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Plates</p>
              <p className="font-medium">{run.plate_count}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Notes</p>
              <p className="font-medium">{run.notes ?? "\u2014"}</p>
            </div>
          </div>
          {run.lock_reason && (
            <div className="mt-4 rounded-md bg-destructive/10 p-3">
              <p className="text-sm font-medium text-destructive">
                Lock reason: {run.lock_reason}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Data visualizations */}
      <RunDataPanel run={run} />

      {/* Files */}
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Paperclip className="h-4 w-4" />
          Files
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Attachments associated with this run.
        </p>
        <div className="mt-4 space-y-6">
          <FileUploadZone entityType="run" entityId={runId} />
          <AttachmentList entityType="run" entityId={runId} />
        </div>
      </div>

      {/* Reject Dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Run</DialogTitle>
            <DialogDescription>
              Provide a reason for rejecting this run.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Reason</Label>
              <Textarea
                placeholder="Reason for rejection..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="destructive"
              onClick={handleReject}
              disabled={!rejectReason.trim() || rejectMutation.isPending}
            >
              {rejectMutation.isPending ? "Rejecting..." : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Lock Dialog */}
      <Dialog open={lockDialogOpen} onOpenChange={setLockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Lock Run</DialogTitle>
            <DialogDescription>
              Provide a reason for locking this run. Locked runs cannot have
              data modified.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Reason</Label>
              <Textarea
                placeholder="Reason for locking..."
                value={lockReason}
                onChange={(e) => setLockReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={handleLock}
              disabled={!lockReason.trim() || lockMutation.isPending}
            >
              {lockMutation.isPending ? "Locking..." : "Lock Run"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Unlock Dialog */}
      <Dialog open={unlockDialogOpen} onOpenChange={setUnlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unlock Run</DialogTitle>
            <DialogDescription>
              Provide a reason for unlocking this run.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Reason</Label>
              <Textarea
                placeholder="Reason for unlocking..."
                value={unlockReason}
                onChange={(e) => setUnlockReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={handleUnlock}
              disabled={!unlockReason.trim() || unlockMutation.isPending}
            >
              {unlockMutation.isPending ? "Unlocking..." : "Unlock Run"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
