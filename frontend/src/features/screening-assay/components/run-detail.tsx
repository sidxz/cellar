"use client";

import { useState } from "react";
import {
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
import { Textarea } from "@/shared/components/ui/textarea";
import { DetailShell } from "@/shared/components/detail-shell";
import { MemberName, ProtocolName } from "@/shared/components/entity-name";
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

export function RunDetail({ runId }: RunDetailProps) {
  const query = useRun(runId);
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
    <>
      <DetailShell
        query={query}
        backHref="/assays"
        backLabel="Back to Protocols"
        title={(r) => `Run ${r.run_date}`}
        badge={(r) => ({ status: r.status })}
        notFoundMessage="Run not found."
        actions={(r) => {
          const status = r.status as RunStatus;
          return (
            <>
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
                      plate_count: r.plate_count,
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
              {status !== "draft" && !r.is_locked && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setLockDialogOpen(true)}
                >
                  <Lock className="mr-2 h-4 w-4" />
                  Lock
                </Button>
              )}
              {status !== "draft" && r.is_locked && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setUnlockDialogOpen(true)}
                >
                  <Unlock className="mr-2 h-4 w-4" />
                  Unlock
                </Button>
              )}
            </>
          );
        }}
      >
        {(run) => (
          <>
            {/* Metadata */}
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Protocol</p>
                    <a
                      href={`/assays/protocols/${run.protocol_id}`}
                      className="text-sm text-primary hover:underline underline-offset-4"
                    >
                      <ProtocolName id={run.protocol_id} />
                    </a>
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
          </>
        )}
      </DetailShell>

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
    </>
  );
}
