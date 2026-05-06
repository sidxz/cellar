"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Play,
  CheckCircle2,
  ThumbsUp,
  ThumbsDown,
  Lock,
  Unlock,
  Calculator,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
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
import {
  useRun,
  useStartRun,
  useCompleteRun,
  useApproveRun,
  useRejectRun,
  useLockRun,
  useUnlockRun,
  useRecomputeRun,
  useDeleteRun,
} from "../hooks/use-runs";
import { useProtocol } from "../hooks/use-protocols";
import {
  PLATE_FORMAT_LABELS,
  type PlateFormat,
  type RunStatus,
} from "../types";
import { RunDataPanel } from "./run-data-panel";
import { ResetRunDataDialog } from "./reset-run-data-dialog";

interface RunDetailProps {
  runId: string;
}

export function RunDetail({ runId }: RunDetailProps) {
  const router = useRouter();
  const query = useRun(runId);
  const { data: protocol } = useProtocol(query.data?.protocol_id ?? "");
  const startMutation = useStartRun();
  const completeMutation = useCompleteRun();
  const approveMutation = useApproveRun();
  const rejectMutation = useRejectRun();
  const lockMutation = useLockRun();
  const unlockMutation = useUnlockRun();
  const recomputeMutation = useRecomputeRun();
  const deleteMutation = useDeleteRun();

  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [lockDialogOpen, setLockDialogOpen] = useState(false);
  const [lockReason, setLockReason] = useState("");
  const [unlockDialogOpen, setUnlockDialogOpen] = useState(false);
  const [unlockReason, setUnlockReason] = useState("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);

  const handleDelete = () => {
    const protocolId = query.data?.protocol_id;
    deleteMutation.mutate(runId, {
      onSuccess: () => {
        setDeleteDialogOpen(false);
        if (protocolId) {
          router.push(`/assays/protocols/${protocolId}`);
        } else {
          router.push("/assays");
        }
      },
    });
  };

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
        backHref={protocol ? `/assays/protocols/${protocol.id}` : "/assays"}
        backLabel={protocol ? `Back to ${protocol.name}` : "Back to Protocols"}
        title={(r) => `Run ${r.run_date}`}
        breadcrumbTrail={(r) => [
          { label: "Protocols", href: "/assays" },
          { label: protocol?.name ?? "...", href: `/assays/protocols/${r.protocol_id}` },
        ]}
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
              {!r.is_locked && r.plate_count > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => recomputeMutation.mutate(runId)}
                  disabled={recomputeMutation.isPending}
                  title="Re-run normalization, replicate aggregation, calculated readouts, and dose-response fitting on existing raw data"
                >
                  <Calculator className="mr-2 h-4 w-4" />
                  {recomputeMutation.isPending ? "Recomputing..." : "Recompute"}
                </Button>
              )}
              {(status === "draft" || status === "in_progress") && !r.is_locked && r.plate_count > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setResetDialogOpen(true)}
                  className="border-destructive/40 text-destructive hover:bg-destructive/10"
                >
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Reset Data
                </Button>
              )}
              {(status === "draft" || status === "in_progress") && !r.is_locked && (
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete
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

            {/* Data visualizations + files */}
            <RunDataPanel run={run} />
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

      {/* Reset Run Data Dialog */}
      <ResetRunDataDialog
        runId={runId}
        open={resetDialogOpen}
        onOpenChange={setResetDialogOpen}
        plateCount={query.data?.plate_count ?? 0}
      />

      {/* Delete Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this run?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the run, its plates, wells, readout
              data, and any fitted curves. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
