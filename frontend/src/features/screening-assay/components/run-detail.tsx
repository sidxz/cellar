"use client";

import { TagTable } from "@/features/tagging/components/tag-table";
import { CascadeDeleteDialog } from "@/shared/components/cascade-delete-dialog";
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import { ProtocolName } from "@/shared/components/entity-name";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
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
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import {
  Calculator,
  CheckCircle2,
  Lock,
  Play,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Unlock,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useProtocol } from "../hooks/use-protocols";
import { useRecomputeOverrides } from "../hooks/use-recompute-overrides";
import { useAddRunTarget, useRemoveRunTarget } from "../hooks/use-run-targets";
import {
  useApproveRun,
  useCompleteRun,
  useDeleteRun,
  useLockRun,
  useRecomputeRun,
  useRejectRun,
  useRun,
  useStartRun,
  useUnlockRun,
} from "../hooks/use-runs";
import { PLATE_FORMAT_LABELS, type PlateFormat, type RunStatus } from "../types";
import { ResetRunDataDialog } from "./reset-run-data-dialog";
import { RunDataPanel } from "./run-data-panel";
import { TargetChips } from "./target-chips";
import { TargetMultiSelect } from "./target-multi-select";

interface RunDetailProps {
  runId: string;
}

export function RunDetail({ runId }: RunDetailProps) {
  const router = useRouter();
  const isAdmin = useAuthzHasRole("admin");
  const canEditTags = useAuthzHasRole("editor");
  const query = useRun(runId);
  const { data: protocol } = useProtocol(query.data?.protocol_id ?? "");
  const addRunTarget = useAddRunTarget(runId);
  const removeRunTarget = useRemoveRunTarget(runId);
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

  // Per-run fit constraint overrides for Recompute. Mirrors the protocol's
  // Free/Range/Lock vocabulary so the popover matches the protocol-design
  // surface; "inherit" means the protocol's setting carries through
  // unchanged for that param. Override values are applied for THIS recompute
  // pass only and are not persisted.
  const [recomputePopoverOpen, setRecomputePopoverOpen] = useState(false);
  const {
    overrides: recomputeOverrides,
    updateOverride,
    clearOverrides: clearRecomputeOverrides,
    buildPayload: buildRecomputePayload,
  } = useRecomputeOverrides();

  const {
    topMode: recomputeTopMode,
    top: recomputeTop,
    topMin: recomputeTopMin,
    topMax: recomputeTopMax,
    bottomMode: recomputeBottomMode,
    bottom: recomputeBottom,
    bottomMin: recomputeBottomMin,
    bottomMax: recomputeBottomMax,
    hillMode: recomputeHillMode,
    hillEnum: recomputeHillEnum,
    hillMin: recomputeHillMin,
    hillMax: recomputeHillMax,
  } = recomputeOverrides;

  const handleRecompute = (withOverrides: boolean) => {
    if (!withOverrides) {
      recomputeMutation.mutate({ runId });
      return;
    }
    recomputeMutation.mutate(
      { runId, overrides: buildRecomputePayload() },
      {
        onSuccess: () => {
          setRecomputePopoverOpen(false);
        },
      },
    );
  };

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
      },
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
      },
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
      },
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
                  <Button size="sm" variant="destructive" onClick={() => setRejectDialogOpen(true)}>
                    <ThumbsDown className="mr-2 h-4 w-4" />
                    Reject
                  </Button>
                </>
              )}
              {status !== "draft" && !r.is_locked && (
                <Button size="sm" variant="outline" onClick={() => setLockDialogOpen(true)}>
                  <Lock className="mr-2 h-4 w-4" />
                  Lock
                </Button>
              )}
              {status !== "draft" && r.is_locked && (
                <Button size="sm" variant="outline" onClick={() => setUnlockDialogOpen(true)}>
                  <Unlock className="mr-2 h-4 w-4" />
                  Unlock
                </Button>
              )}
              {!r.is_locked && r.plate_count > 0 && (
                <div className="inline-flex">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleRecompute(false)}
                    disabled={recomputeMutation.isPending}
                    title="Re-run normalization, replicate aggregation, calculated readouts, and dose-response fitting on existing raw data"
                    className="rounded-r-none border-r-0"
                  >
                    <Calculator className="mr-2 h-4 w-4" />
                    {recomputeMutation.isPending ? "Recomputing..." : "Recompute"}
                  </Button>
                  <Popover open={recomputePopoverOpen} onOpenChange={setRecomputePopoverOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={recomputeMutation.isPending}
                        title="Recompute with one-time fit constraint overrides"
                        className="rounded-l-none px-2"
                      >
                        ▾
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[28rem] space-y-3" align="end">
                      <div>
                        <p className="text-sm font-medium">Override fit constraints</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          One-time overrides for this recompute. &ldquo;Inherit&rdquo; uses the
                          protocol&apos;s setting (Free, Range, or Lock). Not saved on the run or
                          the protocol.
                        </p>
                      </div>

                      {/* Top */}
                      <div className="rounded-md border bg-background p-2 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs font-medium">Top</Label>
                          <RecomputeModeToggle
                            mode={recomputeTopMode}
                            onChange={(v) => updateOverride("topMode", v)}
                            idPrefix="rec-top"
                          />
                        </div>
                        {recomputeTopMode === "lock" && (
                          <Input
                            type="number"
                            className="h-8 text-xs"
                            placeholder="e.g., 100"
                            value={recomputeTop}
                            onChange={(e) => updateOverride("top", e.target.value)}
                          />
                        )}
                        {recomputeTopMode === "range" && (
                          <div className="flex items-center gap-1.5">
                            <Input
                              type="number"
                              className="h-8 text-xs"
                              placeholder="85"
                              value={recomputeTopMin}
                              onChange={(e) => updateOverride("topMin", e.target.value)}
                            />
                            <span className="text-xs text-muted-foreground">to</span>
                            <Input
                              type="number"
                              className="h-8 text-xs"
                              placeholder="110"
                              value={recomputeTopMax}
                              onChange={(e) => updateOverride("topMax", e.target.value)}
                            />
                          </div>
                        )}
                      </div>

                      {/* Bottom */}
                      <div className="rounded-md border bg-background p-2 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs font-medium">Bottom</Label>
                          <RecomputeModeToggle
                            mode={recomputeBottomMode}
                            onChange={(v) => updateOverride("bottomMode", v)}
                            idPrefix="rec-bot"
                          />
                        </div>
                        {recomputeBottomMode === "lock" && (
                          <Input
                            type="number"
                            className="h-8 text-xs"
                            placeholder="e.g., 0"
                            value={recomputeBottom}
                            onChange={(e) => updateOverride("bottom", e.target.value)}
                          />
                        )}
                        {recomputeBottomMode === "range" && (
                          <div className="flex items-center gap-1.5">
                            <Input
                              type="number"
                              className="h-8 text-xs"
                              placeholder="-10"
                              value={recomputeBottomMin}
                              onChange={(e) => updateOverride("bottomMin", e.target.value)}
                            />
                            <span className="text-xs text-muted-foreground">to</span>
                            <Input
                              type="number"
                              className="h-8 text-xs"
                              placeholder="10"
                              value={recomputeBottomMax}
                              onChange={(e) => updateOverride("bottomMax", e.target.value)}
                            />
                          </div>
                        )}
                      </div>

                      {/* Hill */}
                      <div className="rounded-md border bg-background p-2 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <Label className="text-xs font-medium">Hill Slope</Label>
                          <Select
                            value={recomputeHillMode}
                            onValueChange={(v) =>
                              updateOverride("hillMode", v as "inherit" | "enum" | "range")
                            }
                          >
                            <SelectTrigger className="h-7 w-36 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="inherit" className="text-xs">
                                Inherit
                              </SelectItem>
                              <SelectItem value="enum" className="text-xs">
                                Use preset
                              </SelectItem>
                              <SelectItem value="range" className="text-xs">
                                Custom range
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        {recomputeHillMode === "enum" && (
                          <Select
                            value={recomputeHillEnum}
                            onValueChange={(v) =>
                              updateOverride(
                                "hillEnum",
                                v as
                                  | "unconstrained"
                                  | "negative_only"
                                  | "positive_only"
                                  | "fixed_at_one",
                              )
                            }
                          >
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="unconstrained">Unconstrained</SelectItem>
                              <SelectItem value="negative_only">Negative only</SelectItem>
                              <SelectItem value="positive_only">Positive only</SelectItem>
                              <SelectItem value="fixed_at_one">Fixed at 1</SelectItem>
                            </SelectContent>
                          </Select>
                        )}
                        {recomputeHillMode === "range" && (
                          <div className="flex items-center gap-1.5">
                            <Input
                              type="number"
                              step="0.1"
                              className="h-8 text-xs"
                              placeholder="0.9"
                              value={recomputeHillMin}
                              onChange={(e) => updateOverride("hillMin", e.target.value)}
                            />
                            <span className="text-xs text-muted-foreground">to</span>
                            <Input
                              type="number"
                              step="0.1"
                              className="h-8 text-xs"
                              placeholder="1.1"
                              value={recomputeHillMax}
                              onChange={(e) => updateOverride("hillMax", e.target.value)}
                            />
                          </div>
                        )}
                      </div>

                      <div className="flex justify-end gap-2 pt-1">
                        <Button size="sm" variant="ghost" onClick={clearRecomputeOverrides}>
                          Clear
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => handleRecompute(true)}
                          disabled={recomputeMutation.isPending}
                        >
                          Recompute with overrides
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              )}
              {(status === "draft" || status === "in_progress") &&
                !r.is_locked &&
                r.plate_count > 0 && (
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
                <Button size="sm" variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete
                </Button>
              )}
              {isAdmin && (
                <CascadeDeleteDialog
                  entityType="run"
                  entityId={runId}
                  entityLabel={r.notes ?? runId}
                  onDeleted={() =>
                    r.protocol_id
                      ? router.push(`/assays/protocols/${r.protocol_id}`)
                      : router.push("/assays")
                  }
                />
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
                        ? (PLATE_FORMAT_LABELS[run.plate_format as PlateFormat] ?? run.plate_format)
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

            {/* Targets */}
            <Card>
              <CardHeader>
                <CardTitle>Targets</CardTitle>
              </CardHeader>
              <CardContent>
                {canEditTags && !run.is_locked ? (
                  <TargetMultiSelect
                    value={run.targets.map((t) => t.id)}
                    onChange={(ids) => {
                      const current = run.targets.map((t) => t.id);
                      for (const id of ids) {
                        if (!current.includes(id)) addRunTarget.mutate(id);
                      }
                      for (const id of current) {
                        if (!ids.includes(id)) removeRunTarget.mutate(id);
                      }
                    }}
                    placeholder="Add a target…"
                  />
                ) : (
                  <TargetChips targets={run.targets} max={20} />
                )}
              </CardContent>
            </Card>

            {/* Tags */}
            <TagTable entity="runs" entityId={runId} canEdit={canEditTags} />

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
            <DialogDescription>Provide a reason for rejecting this run.</DialogDescription>
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
              Provide a reason for locking this run. Locked runs cannot have data modified.
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
            <Button onClick={handleLock} disabled={!lockReason.trim() || lockMutation.isPending}>
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
      <ConfirmDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete this run?"
        description="This will permanently delete the run, its plates, wells, readout data, and any fitted curves. This cannot be undone."
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />

      {/* Unlock Dialog */}
      <Dialog open={unlockDialogOpen} onOpenChange={setUnlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unlock Run</DialogTitle>
            <DialogDescription>Provide a reason for unlocking this run.</DialogDescription>
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

/** Inherit / Free / Range / Lock toggle for Top and Bottom in the Recompute
 *  popover. "Inherit" is recompute-specific; the protocol-design and
 *  per-curve toggles use the same Free/Range/Lock vocabulary but always
 *  ship a value, never "inherit". */
function RecomputeModeToggle({
  mode,
  onChange,
  idPrefix,
}: {
  mode: "inherit" | "free" | "range" | "lock";
  onChange: (m: "inherit" | "free" | "range" | "lock") => void;
  idPrefix: string;
}) {
  const options: ("inherit" | "free" | "range" | "lock")[] = ["inherit", "free", "range", "lock"];
  return (
    <div className="inline-flex rounded-md border" role="radiogroup">
      {options.map((opt) => (
        <button
          key={`${idPrefix}-${opt}`}
          type="button"
          role="radio"
          aria-checked={mode === opt}
          onClick={() => onChange(opt)}
          className={`px-2 py-0.5 text-[10px] capitalize first:rounded-l-md last:rounded-r-md ${mode === opt ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted"}`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
