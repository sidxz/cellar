"use client";

import { useCddEnabled } from "@/features/screening-assay/hooks/use-cdd-enabled";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { PageHeader } from "@/shared/components/page-header";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { formatDateTime } from "@/shared/lib/format-date";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, Square, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { MOLECULES_KEY } from "../hooks/query-keys";
import {
  useCancelCddMoleculeImport,
  useCddMoleculeImportStatus,
  useForceFailImport,
  useImportHistory,
  useStartCddMoleculeImport,
} from "../hooks/use-cdd-molecule-import";
import {
  useCancelCddPlateImport,
  useCddPlateImportStatus,
  useForceFailPlateImport,
  usePlateImportHistory,
  useStartCddPlateImport,
} from "../hooks/use-cdd-plate-import";

const TERMINAL_STATUSES = ["completed", "completed_with_errors", "failed"];

export function DataImportPage() {
  const qc = useQueryClient();
  const { enabled: cddEnabled, loading: cddLoading } = useCddEnabled();

  // Form state
  const [orgId, setOrgId] = useState("");
  const [importMode, setImportMode] = useState<"full_vault" | "sync">("full_vault");
  const [maxMolecules, setMaxMolecules] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [completionMessage, setCompletionMessage] = useState<string | null>(null);

  // Active import tracking
  const [workflowId, setWorkflowId] = useState<string | null>(null);

  // Queries & mutations
  const { data: orgs } = useOrganizations();
  const { data: history, refetch: refetchHistory } = useImportHistory();
  const startMutation = useStartCddMoleculeImport();
  const forceFailMutation = useForceFailImport();
  const cancelMutation = useCancelCddMoleculeImport();

  // Find active import from history (survives page reload)
  const activeImport = history?.find((imp) => !TERMINAL_STATUSES.includes(imp.status));

  // Auto-resume polling for active imports
  useEffect(() => {
    if (activeImport?.workflow_id && !workflowId) {
      setWorkflowId(activeImport.workflow_id);
    }
  }, [activeImport, workflowId]);

  const { data: liveStatus } = useCddMoleculeImportStatus(workflowId);

  // When complete, clear polling and show result message
  useEffect(() => {
    if (liveStatus && TERMINAL_STATUSES.includes(liveStatus.status)) {
      setWorkflowId(null);
      qc.invalidateQueries({ queryKey: ["cdd-molecule-import", "history"] });
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });

      if (liveStatus.status === "completed") {
        setCompletionMessage(
          `Import completed successfully. ${liveStatus.registered_count} molecules registered, ${liveStatus.duplicate_count} duplicates.`,
        );
      } else if (liveStatus.status === "completed_with_errors") {
        setCompletionMessage(
          `Import completed with ${liveStatus.error_count} errors. ${liveStatus.registered_count} molecules registered, ${liveStatus.duplicate_count} duplicates.`,
        );
      } else {
        setCompletionMessage("Import failed. Check the History tab for details.");
      }
    }
  }, [liveStatus, qc]);

  const handleStart = async () => {
    setError(null);
    setCompletionMessage(null);
    if (!orgId) {
      setError("Organization is required");
      return;
    }
    try {
      const limit = maxMolecules ? Number.parseInt(maxMolecules, 10) : undefined;
      const result = await startMutation.mutateAsync({
        originatingOrgId: orgId,
        importMode: importMode,
        maxMolecules: limit && !Number.isNaN(limit) ? limit : undefined,
      });
      setWorkflowId(result.workflow_id);
      refetchHistory();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start import");
    }
  };

  const handleCancel = async () => {
    if (workflowId) {
      await cancelMutation.mutateAsync(workflowId);
    }
  };

  const isImportActive = !!workflowId;
  const processedCount = liveStatus
    ? liveStatus.registered_count +
      liveStatus.duplicate_count +
      liveStatus.error_count +
      liveStatus.skipped_count
    : 0;
  const percent =
    liveStatus && liveStatus.total_count > 0
      ? Math.round((processedCount / liveStatus.total_count) * 100)
      : 0;

  if (cddLoading) {
    return (
      <>
        <PageHeader title="CDD Vault Import" subtitle="Loading configuration..." />
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Loading...
        </div>
      </>
    );
  }

  if (!cddEnabled) {
    return (
      <>
        <PageHeader
          title="CDD Vault Import"
          subtitle="Import data from your connected CDD Vault."
        />
        <div className="rounded-md border p-8 text-center text-muted-foreground mt-4">
          <p className="font-medium">CDD Vault is not configured</p>
          <p className="text-sm mt-1">
            Configure your CDD Vault API key in Settings &gt; API Keys before importing.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="CDD Vault Import" subtitle="Import data from your connected CDD Vault." />

      {/* Entity type tabs — Molecules & Batches is the only one for now */}
      <Tabs defaultValue="molecules" className="mt-4">
        <TabsList>
          <TabsTrigger value="molecules">Molecules &amp; Batches</TabsTrigger>
          <TabsTrigger value="protocols" disabled>
            Protocols
          </TabsTrigger>
          <TabsTrigger value="plates">Plates</TabsTrigger>
        </TabsList>

        <TabsContent value="molecules" className="mt-4">
          {/* Inner tabs: New Import / History */}
          <Tabs defaultValue="new-import">
            <TabsList>
              <TabsTrigger value="new-import">New Import</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>

            {/* Tab 1: New Import */}
            <TabsContent value="new-import" className="mt-4 space-y-6">
              {completionMessage && (
                <div className="flex items-start gap-2 rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-950/30 dark:text-green-300">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{completionMessage}</span>
                </div>
              )}

              {error && (
                <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              {/* Configuration form (hidden when import active) */}
              {!isImportActive && (
                <div className="max-w-lg space-y-5">
                  <div className="rounded-md border p-4 text-sm space-y-2">
                    <p>This will:</p>
                    <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
                      <li>Discover all molecules in your CDD Vault</li>
                      <li>Register each molecule with structure processing and deduplication</li>
                      <li>Import associated batches (lots, amounts, salts)</li>
                      <li>Register molecules without SMILES as undisclosed</li>
                    </ul>
                    <p className="text-muted-foreground">
                      For large vaults (100K+ molecules), this may take several hours. You can
                      navigate away and check back later.
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
                    <Label>Import Mode</Label>
                    <RadioGroup
                      value={importMode}
                      onValueChange={(v) => setImportMode(v as "full_vault" | "sync")}
                      className="flex gap-6"
                    >
                      <div className="flex items-center gap-2">
                        <RadioGroupItem value="full_vault" id="mode-full" />
                        <Label htmlFor="mode-full" className="font-normal">
                          Full Vault
                        </Label>
                      </div>
                      <div className="flex items-center gap-2">
                        <RadioGroupItem value="sync" id="mode-sync" />
                        <Label htmlFor="mode-sync" className="font-normal">
                          Sync (new molecules only)
                        </Label>
                      </div>
                    </RadioGroup>
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

                  <Button onClick={handleStart} disabled={!orgId || startMutation.isPending}>
                    {startMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Start Import
                  </Button>
                </div>
              )}

              {/* Progress section (visible when import active) */}
              {isImportActive && liveStatus && (
                <div className="max-w-lg space-y-4">
                  {/* Phase indicator */}
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    {TERMINAL_STATUSES.includes(liveStatus.status) ? (
                      statusIcon(liveStatus.status)
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                    {statusLabel(liveStatus.status, liveStatus.pages_processed)}
                  </div>

                  {/* Progress bar */}
                  {liveStatus.total_count > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>
                          {processedCount.toLocaleString()} of{" "}
                          {liveStatus.total_count.toLocaleString()}
                        </span>
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
                      value={liveStatus.registered_count}
                      color="text-green-600"
                    />
                    <CounterCard
                      label="Duplicate"
                      value={liveStatus.duplicate_count}
                      color="text-blue-600"
                    />
                    <CounterCard
                      label="Skipped"
                      value={liveStatus.skipped_count}
                      color="text-muted-foreground"
                    />
                    <CounterCard
                      label="Errors"
                      value={liveStatus.error_count}
                      color="text-destructive"
                    />
                  </div>

                  {!TERMINAL_STATUSES.includes(liveStatus.status) && (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleCancel}
                      disabled={cancelMutation.isPending}
                    >
                      <Square className="mr-1.5 h-3 w-3" />
                      Stop Import
                    </Button>
                  )}
                </div>
              )}

              {/* Waiting for first status poll */}
              {isImportActive && !liveStatus && (
                <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting import workflow...
                </div>
              )}
            </TabsContent>

            {/* Tab 2: History */}
            <TabsContent value="history" className="mt-4">
              {!history || history.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No imports have been run yet.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Mode</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Registered</TableHead>
                      <TableHead className="text-right">Duplicate</TableHead>
                      <TableHead className="text-right">Errors</TableHead>
                      <TableHead className="text-right">Skipped</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.map((imp) => (
                      <TableRow key={imp.id}>
                        <TableCell className="whitespace-nowrap">
                          {formatDateTime(imp.submitted_at)}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {imp.import_mode === "full_vault" ? "Full" : "Sync"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <ImportStatusBadge status={imp.status} />
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {imp.registered_count.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {imp.duplicate_count.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {imp.error_count.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {imp.skipped_count.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {imp.total_count.toLocaleString()}
                        </TableCell>
                        <TableCell>
                          {!TERMINAL_STATUSES.includes(imp.status) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              onClick={() => forceFailMutation.mutate(imp.id)}
                              disabled={forceFailMutation.isPending}
                            >
                              Force Stop
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </TabsContent>
          </Tabs>
        </TabsContent>

        {/* ===== Plates tab ===== */}
        <TabsContent value="plates" className="mt-4">
          <PlateImportTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

/* ---------- Plate import tab ---------- */

function PlateImportTab() {
  const qc = useQueryClient();
  const [plateWorkflowId, setPlateWorkflowId] = useState<string | null>(null);
  const [plateError, setPlateError] = useState<string | null>(null);
  const [plateCompletion, setPlateCompletion] = useState<string | null>(null);

  const { data: plateHistory, refetch: refetchPlateHistory } = usePlateImportHistory();
  const startPlate = useStartCddPlateImport();
  const cancelPlate = useCancelCddPlateImport();
  const forceFailPlate = useForceFailPlateImport();

  const activePlateImport = plateHistory?.find((imp) => !TERMINAL_STATUSES.includes(imp.status));

  useEffect(() => {
    if (activePlateImport?.workflow_id && !plateWorkflowId) {
      setPlateWorkflowId(activePlateImport.workflow_id);
    }
  }, [activePlateImport, plateWorkflowId]);

  const { data: plateLive } = useCddPlateImportStatus(plateWorkflowId);

  useEffect(() => {
    if (plateLive && TERMINAL_STATUSES.includes(plateLive.status)) {
      setPlateWorkflowId(null);
      qc.invalidateQueries({ queryKey: ["cdd-plate-import", "history"] });
      qc.invalidateQueries({ queryKey: ["plates"] });
      if (plateLive.status === "completed") {
        setPlateCompletion(
          `Import completed. ${plateLive.plates_registered} plates registered, ${plateLive.plates_duplicate} duplicates, ${plateLive.wells_mapped} wells mapped.`,
        );
      } else if (plateLive.status === "completed_with_errors") {
        setPlateCompletion(
          `Import completed with ${plateLive.plates_error} errors. ${plateLive.plates_registered} plates registered, ${plateLive.wells_unresolved} wells unresolved.`,
        );
      } else {
        setPlateCompletion("Import failed. Check the History tab for details.");
      }
    }
  }, [plateLive, qc]);

  const handleStartPlate = async () => {
    setPlateError(null);
    setPlateCompletion(null);
    try {
      const result = await startPlate.mutateAsync();
      setPlateWorkflowId(result.workflow_id);
      refetchPlateHistory();
    } catch (err: unknown) {
      setPlateError(err instanceof Error ? err.message : "Failed to start plate import");
    }
  };

  const isPlateActive = !!plateWorkflowId;
  const plateProcessed = plateLive
    ? plateLive.plates_registered + plateLive.plates_duplicate + plateLive.plates_error
    : 0;
  const platePct =
    plateLive && plateLive.total_count > 0
      ? Math.round((plateProcessed / plateLive.total_count) * 100)
      : 0;

  return (
    <Tabs defaultValue="new-import">
      <TabsList>
        <TabsTrigger value="new-import">New Import</TabsTrigger>
        <TabsTrigger value="history">History</TabsTrigger>
      </TabsList>

      <TabsContent value="new-import" className="mt-4 space-y-6">
        {plateCompletion && (
          <div className="flex items-start gap-2 rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-950/30 dark:text-green-300">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{plateCompletion}</span>
          </div>
        )}

        {plateError && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {plateError}
          </div>
        )}

        {!isPlateActive && (
          <div className="max-w-lg space-y-5">
            <div className="rounded-md border p-4 text-sm space-y-2">
              <p>This will:</p>
              <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
                <li>Export all plates from your connected CDD Vault</li>
                <li>Register each plate with barcode and format detection</li>
                <li>Map wells to internal batches via CDD batch ID resolution</li>
                <li>Wells with unresolvable batch IDs will be left unmapped</li>
              </ul>
              <p className="text-muted-foreground">
                Plates are imported using your configured CDD Vault data source.
              </p>
            </div>
            <Button onClick={handleStartPlate} disabled={startPlate.isPending}>
              {startPlate.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Start Plate Import
            </Button>
          </div>
        )}

        {isPlateActive && plateLive && (
          <div className="max-w-lg space-y-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {TERMINAL_STATUSES.includes(plateLive.status) ? (
                statusIcon(plateLive.status)
              ) : (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              {plateLive.status === "processing"
                ? `Registering plates... (chunk ${plateLive.pages_processed})`
                : statusLabel(plateLive.status, plateLive.pages_processed)}
            </div>

            {plateLive.total_count > 0 && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>
                    {plateProcessed.toLocaleString()} of {plateLive.total_count.toLocaleString()}
                  </span>
                  <span>{platePct}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300"
                    style={{ width: `${platePct}%` }}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-4 gap-3">
              <CounterCard
                label="Registered"
                value={plateLive.plates_registered}
                color="text-green-600"
              />
              <CounterCard
                label="Duplicate"
                value={plateLive.plates_duplicate}
                color="text-blue-600"
              />
              <CounterCard
                label="Wells OK"
                value={plateLive.wells_mapped}
                color="text-muted-foreground"
              />
              <CounterCard label="Errors" value={plateLive.plates_error} color="text-destructive" />
            </div>

            {!TERMINAL_STATUSES.includes(plateLive.status) && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => plateWorkflowId && cancelPlate.mutate(plateWorkflowId)}
                disabled={cancelPlate.isPending}
              >
                <Square className="mr-1.5 h-3 w-3" />
                Stop Import
              </Button>
            )}
          </div>
        )}

        {isPlateActive && !plateLive && (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Starting plate import workflow...
          </div>
        )}
      </TabsContent>

      <TabsContent value="history" className="mt-4">
        {!plateHistory || plateHistory.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No plate imports have been run yet.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Registered</TableHead>
                <TableHead className="text-right">Duplicate</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead className="text-right">Wells</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {plateHistory.map((imp) => (
                <TableRow key={imp.id}>
                  <TableCell className="whitespace-nowrap">
                    {formatDateTime(imp.submitted_at)}
                  </TableCell>
                  <TableCell>
                    <ImportStatusBadge status={imp.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {imp.plates_registered.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {imp.plates_duplicate.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {imp.plates_error.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {imp.wells_mapped.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {imp.total_count.toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {!TERMINAL_STATUSES.includes(imp.status) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => forceFailPlate.mutate(imp.id)}
                        disabled={forceFailPlate.isPending}
                      >
                        Force Stop
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </TabsContent>
    </Tabs>
  );
}

/* ---------- Helpers ---------- */

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
      <div className={`text-lg font-semibold tabular-nums ${color}`}>{value.toLocaleString()}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function ImportStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <Badge variant="success">Completed</Badge>;
    case "completed_with_errors":
      return <Badge variant="warning">Completed with errors</Badge>;
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    case "processing":
    case "discovering":
    case "exporting":
      return <Badge variant="outline">{capitalize(status)}</Badge>;
    default:
      return <Badge variant="secondary">{capitalize(status)}</Badge>;
  }
}

function statusIcon(status: string) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-600" />;
    case "completed_with_errors":
      return <AlertTriangle className="h-4 w-4 text-warning" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-destructive" />;
    default:
      return null;
  }
}

function statusLabel(status: string, pagesProcessed: number) {
  switch (status) {
    case "pending":
      return "Starting import...";
    case "discovering":
      return "Discovering molecules in CDD Vault...";
    case "exporting":
      return "Waiting for CDD Vault to prepare export...";
    case "processing":
      return `Registering molecules... (chunk ${pagesProcessed})`;
    case "completed":
      return "Import completed successfully";
    case "completed_with_errors":
      return "Import completed with errors";
    case "failed":
      return "Import failed";
    default:
      return capitalize(status);
  }
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");
}
