"use client";

import { useEffect, useState } from "react";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Square,
} from "lucide-react";
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
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import {
  useStartCddMoleculeImport,
  useCddMoleculeImportStatus,
  useCancelCddMoleculeImport,
} from "../hooks/use-cdd-molecule-import";

interface CddMoleculeImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Phase = "confirm" | "progress" | "done";

export function CddMoleculeImportDialog({
  open,
  onOpenChange,
}: CddMoleculeImportDialogProps) {
  const [phase, setPhase] = useState<Phase>("confirm");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [maxMolecules, setMaxMolecules] = useState<string>("");
  const [orgId, setOrgId] = useState("");

  const { data: orgs } = useOrganizations();
  const startMutation = useStartCddMoleculeImport();
  const cancelMutation = useCancelCddMoleculeImport();
  const { data: status } = useCddMoleculeImportStatus(
    phase === "progress" ? workflowId : null
  );

  // Transition to done when workflow finishes
  useEffect(() => {
    if (
      phase === "progress" &&
      status &&
      (status.status === "completed" ||
        status.status === "completed_with_errors" ||
        status.status === "failed")
    ) {
      setPhase("done");
    }
  }, [phase, status]);

  const reset = () => {
    setPhase("confirm");
    setWorkflowId(null);
    setError(null);
    setOrgId("");
  };

  const handleOpenChange = (v: boolean) => {
    if (!v) reset();
    onOpenChange(v);
  };

  const handleStart = async () => {
    setError(null);
    if (!orgId) {
      setError("Organization is required");
      return;
    }
    try {
      const limit = maxMolecules ? parseInt(maxMolecules, 10) : undefined;
      const result = await startMutation.mutateAsync({
        originatingOrgId: orgId,
        maxMolecules: limit && !isNaN(limit) ? limit : undefined,
      });
      setWorkflowId(result.workflow_id);
      setPhase("progress");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start import");
    }
  };

  const handleCancel = async () => {
    if (workflowId) {
      await cancelMutation.mutateAsync(workflowId);
    }
  };

  const processedCount = status
    ? status.registered_count +
      status.duplicate_count +
      status.error_count +
      status.skipped_count
    : 0;
  const percent =
    status && status.total_count > 0
      ? Math.round((processedCount / status.total_count) * 100)
      : 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Molecules from CDD Vault</DialogTitle>
          <DialogDescription>
            {phase === "confirm" &&
              "Import all molecules and their batches from your connected CDD Vault."}
            {phase === "progress" && "Import is running in the background..."}
            {phase === "done" && "Import complete."}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Phase 1: Confirm */}
        {phase === "confirm" && (
          <div className="space-y-4">
            <div className="rounded-md border p-4 text-sm space-y-2">
              <p>This will:</p>
              <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
                <li>
                  Discover all molecules in your CDD Vault
                </li>
                <li>
                  Register each molecule with structure processing and
                  deduplication
                </li>
                <li>
                  Import associated batches (lots, amounts, salts)
                </li>
                <li>
                  Register molecules without SMILES as undisclosed
                </li>
              </ul>
              <p className="text-muted-foreground">
                For large vaults (100K+ molecules), this may take several hours.
                You can close this dialog and check back later.
              </p>
            </div>

            <div className="grid gap-2">
              <Label>Originating Organization</Label>
              <Select value={orgId} onValueChange={setOrgId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select organization..." />
                </SelectTrigger>
                <SelectContent>
                  {orgs?.map((org: { id: string; name: string }) => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="max-molecules">
                Max molecules{" "}
                <span className="font-normal text-muted-foreground">
                  (optional, for testing)
                </span>
              </Label>
              <Input
                id="max-molecules"
                type="number"
                min={1}
                placeholder="Leave blank to import all"
                value={maxMolecules}
                onChange={(e) => setMaxMolecules(e.target.value)}
              />
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleStart}
                disabled={!orgId || startMutation.isPending}
              >
                {startMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Start Import
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* Phase 2: Progress */}
        {phase === "progress" && status && (
          <div className="space-y-4">
            {/* Phase indicator */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {status.status === "pending" && "Starting import..."}
              {status.status === "discovering" && "Discovering molecules in CDD Vault..."}
              {status.status === "exporting" && "Waiting for CDD Vault to prepare export..."}
              {status.status === "processing" &&
                `Registering molecules... (chunk ${status.pages_processed})`}
            </div>

            {/* Progress bar */}
            {status.total_count > 0 && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{processedCount.toLocaleString()} of {status.total_count.toLocaleString()}</span>
                  <span>{percent}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            )}

            {/* Live counters */}
            <div className="grid grid-cols-4 gap-3">
              <CounterCard
                label="Registered"
                value={status.registered_count}
                color="text-green-600"
              />
              <CounterCard
                label="Duplicate"
                value={status.duplicate_count}
                color="text-blue-600"
              />
              <CounterCard
                label="Skipped"
                value={status.skipped_count}
                color="text-muted-foreground"
              />
              <CounterCard
                label="Errors"
                value={status.error_count}
                color="text-destructive"
              />
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Close (continues in background)
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleCancel}
                disabled={cancelMutation.isPending}
              >
                <Square className="mr-1.5 h-3 w-3" />
                Stop Import
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* Waiting for first status poll */}
        {phase === "progress" && !status && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Starting import workflow...
          </div>
        )}

        {/* Phase 3: Done */}
        {phase === "done" && status && (
          <div className="space-y-4">
            {/* Status icon */}
            <div className="flex items-center gap-2">
              {status.status === "completed" && (
                <>
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                  <span className="font-medium">Import completed successfully</span>
                </>
              )}
              {status.status === "completed_with_errors" && (
                <>
                  <AlertTriangle className="h-5 w-5 text-warning" />
                  <span className="font-medium">Import completed with errors</span>
                </>
              )}
              {status.status === "failed" && (
                <>
                  <XCircle className="h-5 w-5 text-destructive" />
                  <span className="font-medium">Import failed</span>
                </>
              )}
            </div>

            {/* Final counters */}
            <div className="grid grid-cols-4 gap-3">
              <CounterCard
                label="Registered"
                value={status.registered_count}
                color="text-green-600"
              />
              <CounterCard
                label="Duplicate"
                value={status.duplicate_count}
                color="text-blue-600"
              />
              <CounterCard
                label="Skipped"
                value={status.skipped_count}
                color="text-muted-foreground"
              />
              <CounterCard
                label="Errors"
                value={status.error_count}
                color="text-destructive"
              />
            </div>

            <p className="text-xs text-muted-foreground">
              {status.total_count.toLocaleString()} total molecules processed
              from CDD Vault
            </p>

            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function CounterCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="rounded-md border p-2.5 text-center">
      <div className={`text-lg font-semibold tabular-nums ${color}`}>
        {value.toLocaleString()}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
