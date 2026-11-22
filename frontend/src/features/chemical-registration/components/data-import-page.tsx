"use client";

import { useCddEnabled } from "@/features/screening-assay/hooks/use-cdd-enabled";
import { PageHeader } from "@/shared/components/page-header";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgName } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatDateTime } from "@/shared/lib/format-date";
import { isTerminalImportStatus } from "@/shared/lib/job-status";
import { useBreadcrumbTrail } from "@/shared/lib/stores/breadcrumb-store";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { Database, Eye, History, Loader2, Plus, Settings2, Square } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { MOLECULES_KEY } from "../hooks/query-keys";
import { useCddImportPreview } from "../hooks/use-cdd-import-preview";
import {
  type CddMoleculeIdentifierCheck,
  type CddMoleculeImportStatus,
  type CddMoleculeImportSummary,
  useCancelCddMoleculeImport,
  useCddMoleculeImportStatus,
  useForceFailImport,
  useImportHistory,
  useResumeCddMoleculeImport,
  useStartCddMoleculeImport,
} from "../hooks/use-cdd-molecule-import";
import {
  type CddPlateImportStatus,
  type CddPlateImportSummary,
  useCancelCddPlateImport,
  useCddPlateImportStatus,
  useForceFailPlateImport,
  usePlateImportHistory,
  useStartCddPlateImport,
} from "../hooks/use-cdd-plate-import";
import {
  IMPORT_SCOPES,
  type ImportMode,
  importOutcome,
  importScopeLabel,
} from "../lib/cdd-import-presentation";
import {
  ImportStatusBadge,
  MoleculeImportReport,
  OutcomeNotice,
  PlateImportReport,
  ReportStat,
} from "./cdd-import-report";
import { type DiscloserChoice, DiscloserPick } from "./discloser-pick";
import { PreviewTable } from "./preview-table";
import { NotFoundIdentifiers, SelectedMoleculesImport } from "./selected-molecules-import";

const BREADCRUMBS = [{ label: "Administration" }, { label: "Data import" }, { label: "CDD Vault" }];
const SAMPLE_DESCRIPTION =
  "A sample of up to 20 molecules from CDD Vault. Each row represents a batch, or a molecule without batches.";
type MoleculeRun = CddMoleculeImportSummary | CddMoleculeImportStatus;
type PlateRun = CddPlateImportSummary | CddPlateImportStatus;

export function DataImportPage() {
  useBreadcrumbTrail(BREADCRUMBS);
  const qc = useQueryClient();
  const { enabled: cddEnabled, loading: cddLoading, source } = useCddEnabled();
  const isAdmin = useAuthzHasRole("admin");
  const [discloser, setDiscloser] = useState<DiscloserChoice>({ userId: null, orgId: null });
  const [importMode, setImportMode] = useState<ImportMode>("full_vault");
  const [maxMolecules, setMaxMolecules] = useState("");
  const [identifiers, setIdentifiers] = useState("");
  const [lastCheck, setLastCheck] = useState<{
    text: string;
    result: CddMoleculeIdentifierCheck;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CddMoleculeImportStatus | null>(null);
  const [reportRun, setReportRun] = useState<MoleculeRun | null>(null);
  const [notFound, setNotFound] = useState<string[]>([]);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [view, setView] = useState("new-import");
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const previewMutation = useCddImportPreview();
  const { data: me } = useCurrentUser();
  const memberName = useMemberNames();
  const orgName = useOrgName();
  const historyQuery = useImportHistory();
  const { data: history, refetch: refetchHistory } = historyQuery;
  const startMutation = useStartCddMoleculeImport();
  const forceFailMutation = useForceFailImport();
  const resumeMutation = useResumeCddMoleculeImport();
  const cancelMutation = useCancelCddMoleculeImport();
  const finishedWorkflowId = useRef<string | null>(null);
  const activeImport = history?.find((imp) => !isTerminalImportStatus(imp.status));
  const lastFinished = history?.find((imp) => isTerminalImportStatus(imp.status));
  const isSpecific = importMode === "filtered";
  const checked = lastCheck?.text === identifiers ? lastCheck.result : null;
  const currentPreviewKey = JSON.stringify([
    importMode,
    isSpecific ? identifiers : null,
    discloser,
    maxMolecules,
  ]);
  const previewCurrent = previewKey === currentPreviewKey;
  const invalidLimit =
    !isSpecific &&
    maxMolecules !== "" &&
    (!Number.isSafeInteger(Number(maxMolecules)) || Number(maxMolecules) < 1);
  const scope = IMPORT_SCOPES.find((item) => item.value === importMode) ?? IMPORT_SCOPES[0];
  const discloserLabel = `${
    discloser.userId && discloser.userId !== me?.user_id ? memberName(discloser.userId) : "You"
  } · ${orgName(discloser.orgId ?? me?.org_id) || "your org"}`;

  useEffect(() => {
    if (
      activeImport?.workflow_id &&
      !workflowId &&
      activeImport.workflow_id !== finishedWorkflowId.current
    ) {
      setWorkflowId(activeImport.workflow_id);
    }
  }, [activeImport, workflowId]);

  const statusQuery = useCddMoleculeImportStatus(workflowId);
  const { data: liveStatus } = statusQuery;
  useEffect(() => {
    if (!workflowId || !liveStatus || !isTerminalImportStatus(liveStatus.status)) return;
    finishedWorkflowId.current = workflowId;
    setWorkflowId(null);
    setResult(liveStatus);
    qc.invalidateQueries({ queryKey: ["cdd-molecule-import", "history"] });
    qc.invalidateQueries({ queryKey: MOLECULES_KEY });
  }, [liveStatus, qc, workflowId]);

  const resumeImport = async (importId: string) => {
    setError(null);
    try {
      const accepted = await resumeMutation.mutateAsync(importId);
      qc.removeQueries({ queryKey: ["cdd-molecule-import", "status", accepted.workflow_id] });
      finishedWorkflowId.current = null;
      setResult(null);
      setReportRun(null);
      setNotFound([]);
      setWorkflowId(accepted.workflow_id);
      setView("new-import");
    } catch {
      // The history and report show the server's recovery error.
    }
  };

  const handleStart = async () => {
    if (invalidLimit || (isSpecific && !checked?.found.length)) return;
    setError(null);
    setResult(null);
    setNotFound(isSpecific ? (checked?.not_found ?? []) : []);
    try {
      const accepted = await startMutation.mutateAsync({
        discloser,
        importMode,
        ...(isSpecific
          ? { filterCriteria: { names: checked?.found ?? [] } }
          : { maxMolecules: maxMolecules ? Number(maxMolecules) : undefined }),
      });
      setWorkflowId(accepted.workflow_id);
      refetchHistory();
      if (isSpecific) {
        setIdentifiers("");
        setLastCheck(null);
      }
      previewMutation.reset();
      setPreviewKey(null);
    } catch (err) {
      setNotFound([]);
      setError(err instanceof Error ? err.message : "Could not start the import. Try again.");
    }
  };

  const handleCancel = async () => {
    if (!workflowId) return;
    setError(null);
    try {
      await cancelMutation.mutateAsync(workflowId);
      setStoppingId(workflowId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not stop the import. Try again.");
    }
  };

  const isImportActive = !!workflowId;
  const latestRun = result ?? lastFinished;
  const openReport = (run: MoleculeRun) => {
    // Prefer the saved summary: it also includes scope, timestamps, and organization.
    const saved = history?.find((item) => item.id === ("id" in run ? run.id : run.import_id));
    setReportRun(saved ? { ...saved, ...run } : run);
  };
  const reportSummary = reportRun && "id" in reportRun ? reportRun : undefined;
  const sourceName = source?.name ?? "CDD Vault";
  const vaultId = source?.config.vault_id ? String(source.config.vault_id) : undefined;
  const mappingHref = source ? `/admin/data-sources/${source.id}` : "/admin/data-sources";
  const prerequisite = invalidLimit
    ? "Enter a whole number of at least 1 for the molecule limit."
    : isSpecific && !checked?.found.length
      ? "Check the names in CDD Vault before starting the import."
      : null;

  if (cddLoading)
    return (
      <>
        <PageHeader title="Import from CDD Vault" subtitle="Loading the import configuration…" />
        <LoadingState>Loading CDD Vault…</LoadingState>
      </>
    );
  if (!cddEnabled)
    return (
      <>
        <PageHeader
          title="Import from CDD Vault"
          subtitle="Bring compounds, batches, and plates into ChemCellar."
        />
        <div className="mt-6 max-w-2xl space-y-3 rounded-lg border p-6">
          <h2 className="font-medium">Set up CDD Vault</h2>
          <p className="text-sm text-foreground/70">
            An active CDD Vault data source and API key are required before importing.
          </p>
          {isAdmin ? (
            <Button variant="outline" asChild>
              <Link href="/admin/data-sources">Configure data source</Link>
            </Button>
          ) : (
            <p className="text-sm">Ask an administrator to configure the CDD Vault data source.</p>
          )}
        </div>
      </>
    );

  return (
    <div className="mx-auto w-full max-w-7xl">
      <PageHeader
        title="Import from CDD Vault"
        subtitle="Bring compounds, batches, and plates into ChemCellar."
      />
      <Tabs defaultValue="molecules" className="mt-5">
        <TabsList
          variant="line"
          aria-label="Data type"
          className="w-full justify-start border-b pb-2"
        >
          <TabsTrigger value="molecules" className="flex-none px-3">
            Compounds &amp; batches
          </TabsTrigger>
          <TabsTrigger value="plates" className="flex-none px-3">
            Plates
          </TabsTrigger>
        </TabsList>
        <TabsContent value="molecules" className="mt-4">
          <Tabs value={view} onValueChange={setView}>
            <ImportViewTabs />
            <TabsContent value="new-import" className="mt-4 space-y-5">
              {error && <ErrorMessage>{error}</ErrorMessage>}
              {result && !isImportActive && (
                <OutcomeNotice
                  status={result.status}
                  reason={result.failure_reason}
                  errors={result.error_count}
                >
                  <p>
                    {result.registered_count.toLocaleString()} molecules imported;{" "}
                    {result.duplicate_count.toLocaleString()} matched existing records;{" "}
                    {result.error_count.toLocaleString()} could not be imported.
                  </p>
                  <Button variant="outline" size="sm" onClick={() => openReport(result)}>
                    View report
                  </Button>
                </OutcomeNotice>
              )}
              {(isImportActive || result) && (
                <NotFoundIdentifiers
                  title={`${notFound.length.toLocaleString()} ${notFound.length === 1 ? "name was" : "names were"} not found in CDD Vault and excluded from this import`}
                  identifiers={notFound}
                />
              )}
              {isImportActive ? (
                <ImportProgress
                  status={liveStatus?.status}
                  entity="molecules"
                  total={liveStatus?.total_count ?? 0}
                  processed={
                    liveStatus
                      ? liveStatus.registered_count +
                        liveStatus.duplicate_count +
                        liveStatus.error_count +
                        liveStatus.skipped_count
                      : 0
                  }
                  stopping={stoppingId === workflowId}
                  onStop={handleCancel}
                  stopPending={cancelMutation.isPending}
                  error={statusQuery.isError}
                >
                  {liveStatus && (
                    <>
                      <ReportStat label="Molecules imported" value={liveStatus.registered_count} />
                      <ReportStat label="Matched existing" value={liveStatus.duplicate_count} />
                      <ReportStat label="Molecules skipped" value={liveStatus.skipped_count} />
                      <ReportStat label="Molecule errors" value={liveStatus.error_count} />
                    </>
                  )}
                </ImportProgress>
              ) : (
                <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
                  <section
                    className="min-w-0 rounded-lg border bg-background"
                    aria-labelledby="import-config-title"
                  >
                    <div className="border-b px-5 py-4">
                      <h2 id="import-config-title" className="font-semibold">
                        Configure import
                      </h2>
                      <p className="mt-1 text-sm text-foreground/70">
                        Choose who disclosed the structures and the molecules to import.
                      </p>
                    </div>
                    <div className="space-y-5 p-5">
                      <DiscloserPick value={discloser} onChange={setDiscloser} />
                      <fieldset className="space-y-3">
                        <legend className="mb-1 text-sm font-medium">Import scope</legend>
                        <RadioGroup
                          value={importMode}
                          onValueChange={(value) => setImportMode(value as ImportMode)}
                          aria-label="Import scope"
                          className="gap-2"
                        >
                          {IMPORT_SCOPES.map((option) => (
                            <div
                              key={option.value}
                              className={`relative flex items-start gap-3 rounded-lg border p-3 transition-colors ${importMode === option.value ? "border-primary bg-primary/5" : "hover:bg-muted/40"}`}
                            >
                              <RadioGroupItem
                                value={option.value}
                                id={`mode-${option.value}`}
                                aria-describedby={`mode-${option.value}-help`}
                                className="mt-0.5"
                              />
                              <div className="space-y-1">
                                <Label
                                  htmlFor={`mode-${option.value}`}
                                  className="cursor-pointer after:absolute after:inset-0"
                                >
                                  {option.label}
                                </Label>
                                <p
                                  id={`mode-${option.value}-help`}
                                  className="text-sm text-foreground/70"
                                >
                                  {option.description}
                                </p>
                              </div>
                            </div>
                          ))}
                        </RadioGroup>
                        {importMode === "sync" && (
                          <p className="text-sm text-foreground/70">
                            If no sync timestamp has been saved, this reads the entire vault.
                          </p>
                        )}
                      </fieldset>
                      {isSpecific ? (
                        <SelectedMoleculesImport
                          text={identifiers}
                          onTextChange={setIdentifiers}
                          checked={checked}
                          onChecked={(text, answer) => setLastCheck({ text, result: answer })}
                        />
                      ) : (
                        <details className="rounded-lg border p-4">
                          <summary className="cursor-pointer text-sm font-medium">
                            Advanced options
                          </summary>
                          <div className="mt-4 grid gap-2">
                            <Label htmlFor="max-molecules">
                              Molecule limit{" "}
                              <span className="font-normal text-foreground/70">(optional)</span>
                            </Label>
                            <Input
                              id="max-molecules"
                              type="number"
                              min={1}
                              step={1}
                              placeholder="No limit"
                              value={maxMolecules}
                              aria-invalid={invalidLimit}
                              aria-describedby="limit-help"
                              onChange={(event) => setMaxMolecules(event.target.value)}
                            />
                            <p
                              id="limit-help"
                              className={`text-sm ${invalidLimit ? "text-destructive" : "text-foreground/70"}`}
                            >
                              {invalidLimit
                                ? "Enter a whole number of at least 1."
                                : "Use a smaller import to test your configuration. Leave blank to import all molecules in the selected scope."}
                            </p>
                          </div>
                        </details>
                      )}
                    </div>
                    <div className="space-y-3 border-t px-5 py-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <Button
                          variant="outline"
                          onClick={() => {
                            setPreviewKey(currentPreviewKey);
                            previewMutation.mutate({ names: isSpecific ? checked?.found : null });
                          }}
                          disabled={
                            previewMutation.isPending || (isSpecific && !checked?.found.length)
                          }
                        >
                          {previewMutation.isPending ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Eye className="size-4" />
                          )}
                          Preview sample
                        </Button>
                        <Button
                          onClick={handleStart}
                          disabled={!!prerequisite || startMutation.isPending}
                          aria-describedby={prerequisite ? "import-prerequisite" : undefined}
                        >
                          {startMutation.isPending && <Loader2 className="size-4 animate-spin" />}
                          Start import
                        </Button>
                        {isSpecific && checked && (
                          <span className="text-sm tabular-nums text-foreground/70">
                            {checked.found.length.toLocaleString()} found
                          </span>
                        )}
                      </div>
                      {prerequisite && (
                        <p id="import-prerequisite" className="text-sm text-foreground/70">
                          {prerequisite}
                        </p>
                      )}
                      <p className="text-sm text-foreground/70">
                        Preview shows a sample only. It does not import records.
                      </p>
                    </div>
                  </section>
                  <aside className="space-y-4" aria-label="Import summary">
                    <section className="space-y-4 rounded-lg border bg-muted/20 p-5">
                      <div className="flex items-center gap-2">
                        <Database className="size-4 text-foreground/70" />
                        <h2 className="text-sm font-semibold">Import summary</h2>
                      </div>
                      <dl className="space-y-4 text-sm">
                        <SummaryDetail label="Data source">
                          {sourceName}
                          {vaultId && (
                            <span className="mt-1 block text-foreground/70">Vault {vaultId}</span>
                          )}
                        </SummaryDetail>
                        <SummaryDetail label="Disclosed by">{discloserLabel}</SummaryDetail>
                        <SummaryDetail label="Scope">
                          {scope.label}
                          {isSpecific && checked && (
                            <span className="mt-1 block text-foreground/70">
                              {checked.found.length.toLocaleString()} names found
                            </span>
                          )}
                          {!isSpecific && maxMolecules && !invalidLimit && (
                            <span className="mt-1 block text-foreground/70">
                              Up to {Number(maxMolecules).toLocaleString()} molecules
                            </span>
                          )}
                        </SummaryDetail>
                      </dl>
                      {isAdmin && (
                        <Link
                          href={mappingHref}
                          className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
                        >
                          <Settings2 className="size-4" />
                          Review field mapping
                        </Link>
                      )}
                      <p className="border-t pt-4 text-sm text-foreground/70">
                        This import does not change data in CDD Vault.
                      </p>
                    </section>
                    {latestRun && (
                      <section className="space-y-3 rounded-lg border p-5">
                        <h2 className="text-sm font-semibold">Last import</h2>
                        <ImportStatusBadge
                          status={latestRun.status}
                          reason={latestRun.failure_reason}
                          errors={latestRun.error_count}
                        />
                        {"submitted_at" in latestRun && (
                          <p className="text-sm text-foreground/70">
                            {formatDateTime(latestRun.completed_at ?? latestRun.submitted_at)}
                          </p>
                        )}
                        <p className="text-sm">
                          {latestRun.registered_count.toLocaleString()} imported ·{" "}
                          {latestRun.duplicate_count.toLocaleString()} matched
                          {latestRun.error_count > 0 &&
                            ` · ${latestRun.error_count.toLocaleString()} errors`}
                        </p>
                        <Button variant="outline" size="sm" onClick={() => openReport(latestRun)}>
                          View report
                        </Button>
                      </section>
                    )}
                    <details className="rounded-lg border p-5 text-sm">
                      <summary className="cursor-pointer font-medium">How importing works</summary>
                      <div className="mt-3 space-y-3 text-foreground/70">
                        <p>
                          New molecules become compounds in ChemCellar. Existing compounds and
                          batches are matched using the configured matching rules.
                        </p>
                        <p>
                          Associated batches include amounts and salt information where available.
                          Molecules without a structure are imported as undisclosed compounds.
                        </p>
                        <p>
                          Large vaults may take several hours. You can leave this page and return to
                          check progress.
                        </p>
                      </div>
                    </details>
                  </aside>
                </div>
              )}
              {!isImportActive && previewCurrent && previewMutation.isError && (
                <ErrorMessage>
                  {previewMutation.error?.message ??
                    "Could not read a sample from CDD Vault. Try again."}
                </ErrorMessage>
              )}
              {!isImportActive && previewCurrent && previewMutation.data && (
                <section className="space-y-4 rounded-lg border p-5" aria-labelledby="sample-title">
                  <div>
                    <h2 id="sample-title" className="font-semibold">
                      Sample preview
                    </h2>
                    <p className="mt-1 text-sm text-foreground/70">{SAMPLE_DESCRIPTION}</p>
                    <p className="mt-1 text-sm text-foreground/70">
                      {isSpecific
                        ? "The sample uses the names you checked."
                        : "The sample uses the first molecules in the vault, regardless of sync timestamp or molecule limit."}
                    </p>
                  </div>
                  <PreviewTable
                    items={previewMutation.data.items}
                    createBatchOnDuplicate={source?.create_batch_on_duplicate ?? false}
                  />
                </section>
              )}
            </TabsContent>
            <TabsContent value="history" className="mt-4 space-y-4">
              <div>
                <h2 className="font-semibold">Import history</h2>
                <p className="mt-1 text-sm text-foreground/70">
                  Open a report to review outcomes, import issues, and recovery options.
                </p>
              </div>
              {resumeMutation.error && <ErrorMessage>{resumeMutation.error.message}</ErrorMessage>}
              {forceFailMutation.error && (
                <ErrorMessage>{forceFailMutation.error.message}</ErrorMessage>
              )}
              {historyQuery.isLoading ? (
                <LoadingState>Loading import history…</LoadingState>
              ) : historyQuery.isError ? (
                <ErrorMessage>
                  Could not load import history.{" "}
                  <Button variant="link" onClick={() => refetchHistory()}>
                    Try again
                  </Button>
                </ErrorMessage>
              ) : !history?.length ? (
                <EmptyHistory />
              ) : (
                <div className="overflow-x-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Started</TableHead>
                        <TableHead>Scope</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Imported</TableHead>
                        <TableHead className="text-right">Matched existing</TableHead>
                        <TableHead className="text-right">Errors</TableHead>
                        <TableHead className="text-right">Skipped</TableHead>
                        <TableHead className="text-right">Total molecules</TableHead>
                        <TableHead>
                          <span className="sr-only">Report</span>
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {history.map((imp) => (
                        <TableRow key={imp.id}>
                          <TableCell className="whitespace-nowrap">
                            {formatDateTime(imp.submitted_at)}
                          </TableCell>
                          <TableCell>{importScopeLabel(imp.import_mode)}</TableCell>
                          <TableCell>
                            <ImportStatusBadge
                              status={imp.status}
                              reason={imp.failure_reason}
                              errors={imp.error_count}
                            />
                          </TableCell>
                          {Object.entries({
                            imported: imp.registered_count,
                            matched: imp.duplicate_count,
                            errors: imp.error_count,
                            skipped: imp.skipped_count,
                            total: imp.total_count,
                          }).map(([key, value]) => (
                            <TableCell key={key} className="text-right tabular-nums">
                              {value.toLocaleString()}
                            </TableCell>
                          ))}
                          <TableCell>
                            <Button variant="outline" size="sm" onClick={() => openReport(imp)}>
                              View report
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </TabsContent>
          </Tabs>
          <MoleculeImportReport
            run={reportRun}
            onClose={() => setReportRun(null)}
            organizationName={
              reportSummary?.disclosed_by_org_id
                ? orgName(reportSummary.disclosed_by_org_id)
                : undefined
            }
            recovery={
              <div className="space-y-3">
                {reportSummary?.resumable && !activeImport && (
                  <div className="space-y-2 border-t pt-4">
                    <p className="text-sm text-foreground/70">
                      Continue from the saved position after{" "}
                      {reportSummary.last_processed_offset.toLocaleString()} processed molecules.
                    </p>
                    <Button
                      variant="outline"
                      onClick={() => resumeImport(reportSummary.id)}
                      disabled={resumeMutation.isPending}
                    >
                      {resumeMutation.isPending && <Loader2 className="size-4 animate-spin" />}
                      Resume import
                    </Button>
                  </div>
                )}
                {resumeMutation.error && (
                  <ErrorMessage>{resumeMutation.error.message}</ErrorMessage>
                )}
                {isAdmin && reportSummary && !isTerminalImportStatus(reportSummary.status) && (
                  <AdminRecovery
                    pending={forceFailMutation.isPending}
                    onMark={() =>
                      forceFailMutation.mutate(reportSummary.id, {
                        onSuccess: () => setReportRun(null),
                      })
                    }
                  />
                )}
                {forceFailMutation.error && (
                  <ErrorMessage>{forceFailMutation.error.message}</ErrorMessage>
                )}
              </div>
            }
          />
        </TabsContent>
        <TabsContent value="plates" className="mt-4">
          <PlateImportTab
            sourceName={sourceName}
            vaultId={vaultId}
            mappingHref={isAdmin ? mappingHref : undefined}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PlateImportTab({
  sourceName,
  vaultId,
  mappingHref,
}: { sourceName: string; vaultId?: string; mappingHref?: string }) {
  const qc = useQueryClient();
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CddPlateImportStatus | null>(null);
  const [reportRun, setReportRun] = useState<PlateRun | null>(null);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const finishedWorkflowId = useRef<string | null>(null);
  const historyQuery = usePlateImportHistory();
  const { data: history } = historyQuery;
  const start = useStartCddPlateImport();
  const cancel = useCancelCddPlateImport();
  const forceFail = useForceFailPlateImport();
  const isAdmin = useAuthzHasRole("admin");
  const active = history?.find((imp) => !isTerminalImportStatus(imp.status));
  const latest = result ?? history?.find((imp) => isTerminalImportStatus(imp.status));
  useEffect(() => {
    if (active?.workflow_id && !workflowId && active.workflow_id !== finishedWorkflowId.current)
      setWorkflowId(active.workflow_id);
  }, [active, workflowId]);
  const statusQuery = useCddPlateImportStatus(workflowId);
  const { data: status } = statusQuery;
  useEffect(() => {
    if (!workflowId || !status || !isTerminalImportStatus(status.status)) return;
    finishedWorkflowId.current = workflowId;
    setWorkflowId(null);
    setResult(status);
    qc.invalidateQueries({ queryKey: ["cdd-plate-import", "history"] });
    qc.invalidateQueries({ queryKey: ["plates"] });
  }, [status, qc, workflowId]);
  const handleStart = async () => {
    setError(null);
    setResult(null);
    try {
      const accepted = await start.mutateAsync();
      setWorkflowId(accepted.workflow_id);
      historyQuery.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the plate import. Try again.");
    }
  };
  const handleStop = async () => {
    if (!workflowId) return;
    setError(null);
    try {
      await cancel.mutateAsync(workflowId);
      setStoppingId(workflowId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not stop the plate import. Try again.");
    }
  };
  const openReport = (run: PlateRun) => {
    const saved = history?.find((item) => item.id === ("id" in run ? run.id : run.import_id));
    setReportRun(saved ? { ...saved, ...run } : run);
  };
  return (
    <Tabs defaultValue="new-import">
      <ImportViewTabs />
      <TabsContent value="new-import" className="mt-4 space-y-5">
        {error && <ErrorMessage>{error}</ErrorMessage>}
        {result && !workflowId && (
          <OutcomeNotice
            status={result.status}
            reason={result.failure_reason}
            errors={result.plates_error}
          >
            <p>
              {result.plates_registered.toLocaleString()} plates imported;{" "}
              {result.plates_duplicate.toLocaleString()} matched existing plates;{" "}
              {result.wells_unresolved.toLocaleString()} wells without a batch match.
            </p>
            <Button variant="outline" size="sm" onClick={() => openReport(result)}>
              View report
            </Button>
          </OutcomeNotice>
        )}
        {workflowId ? (
          <ImportProgress
            status={status?.status}
            entity="plates"
            processed={
              status ? status.plates_registered + status.plates_duplicate + status.plates_error : 0
            }
            total={status?.total_count ?? 0}
            stopping={stoppingId === workflowId}
            onStop={handleStop}
            stopPending={cancel.isPending}
            error={statusQuery.isError}
          >
            {status && (
              <>
                <ReportStat label="Plates imported" value={status.plates_registered} />
                <ReportStat label="Matched existing" value={status.plates_duplicate} />
                <ReportStat label="Wells matched to batches" value={status.wells_mapped} />
                <ReportStat label="Plate errors" value={status.plates_error} />
              </>
            )}
          </ImportProgress>
        ) : (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
            <section className="rounded-lg border">
              <div className="border-b p-5">
                <h2 className="font-semibold">Import plates</h2>
                <p className="mt-1 text-sm text-foreground/70">
                  Import all plates from CDD Vault and match their wells to ChemCellar batches.
                </p>
              </div>
              <div className="space-y-4 p-5 text-sm">
                <p>Plates are registered using their barcodes and detected plate formats.</p>
                <div className="rounded-md bg-muted/40 p-4">
                  <h3 className="font-medium">Before importing</h3>
                  <p className="mt-1 text-foreground/70">
                    Import the corresponding compounds and batches first. Wells without a matching
                    CDD batch ID are left without a batch match.
                  </p>
                </div>
                <Button onClick={handleStart} disabled={start.isPending}>
                  {start.isPending && <Loader2 className="size-4 animate-spin" />}Start plate import
                </Button>
                <p className="text-foreground/70">
                  You can leave this page and return to check progress.
                </p>
              </div>
            </section>
            <aside className="space-y-4">
              <section className="space-y-4 rounded-lg border bg-muted/20 p-5">
                <h2 className="text-sm font-semibold">Import summary</h2>
                <dl className="space-y-4 text-sm">
                  <SummaryDetail label="Data source">
                    {sourceName}
                    {vaultId && (
                      <span className="mt-1 block text-foreground/70">Vault {vaultId}</span>
                    )}
                  </SummaryDetail>
                  <SummaryDetail label="Scope">All plates</SummaryDetail>
                </dl>
                {mappingHref && (
                  <Link href={mappingHref} className="text-sm text-primary hover:underline">
                    Review field mapping
                  </Link>
                )}
                <p className="border-t pt-4 text-sm text-foreground/70">
                  This import does not change data in CDD Vault.
                </p>
              </section>
              {latest && (
                <section className="space-y-3 rounded-lg border p-5">
                  <h2 className="text-sm font-semibold">Last import</h2>
                  <ImportStatusBadge
                    status={latest.status}
                    reason={latest.failure_reason}
                    errors={latest.plates_error}
                  />
                  <p className="text-sm">
                    {latest.plates_registered.toLocaleString()} imported ·{" "}
                    {latest.plates_duplicate.toLocaleString()} matched
                  </p>
                  <Button variant="outline" size="sm" onClick={() => openReport(latest)}>
                    View report
                  </Button>
                </section>
              )}
            </aside>
          </div>
        )}
      </TabsContent>
      <TabsContent value="history" className="mt-4 space-y-4">
        <div>
          <h2 className="font-semibold">Plate import history</h2>
          <p className="mt-1 text-sm text-foreground/70">
            Review imported plates and wells that could not be matched.
          </p>
        </div>
        {historyQuery.isLoading ? (
          <LoadingState>Loading plate import history…</LoadingState>
        ) : historyQuery.isError ? (
          <ErrorMessage>
            Could not load plate import history.{" "}
            <Button variant="link" onClick={() => historyQuery.refetch()}>
              Try again
            </Button>
          </ErrorMessage>
        ) : !history?.length ? (
          <EmptyHistory />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Started</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Imported</TableHead>
                  <TableHead className="text-right">Matched existing</TableHead>
                  <TableHead className="text-right">Errors</TableHead>
                  <TableHead className="text-right">Wells matched</TableHead>
                  <TableHead className="text-right">Wells unmatched</TableHead>
                  <TableHead>
                    <span className="sr-only">Report</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((imp) => (
                  <TableRow key={imp.id}>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(imp.submitted_at)}
                    </TableCell>
                    <TableCell>
                      <ImportStatusBadge
                        status={imp.status}
                        reason={imp.failure_reason}
                        errors={imp.plates_error}
                      />
                    </TableCell>
                    {Object.entries({
                      imported: imp.plates_registered,
                      matched: imp.plates_duplicate,
                      errors: imp.plates_error,
                      wellsMatched: imp.wells_mapped,
                      wellsUnmatched: imp.wells_unresolved ?? 0,
                    }).map(([key, value]) => (
                      <TableCell key={key} className="text-right tabular-nums">
                        {value.toLocaleString()}
                      </TableCell>
                    ))}
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => openReport(imp)}>
                        View report
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </TabsContent>
      <PlateImportReport
        run={reportRun}
        onClose={() => setReportRun(null)}
        recovery={
          isAdmin && reportRun && "id" in reportRun && !isTerminalImportStatus(reportRun.status) ? (
            <>
              <AdminRecovery
                pending={forceFail.isPending}
                onMark={() =>
                  forceFail.mutate(reportRun.id, { onSuccess: () => setReportRun(null) })
                }
              />
              {forceFail.error && <ErrorMessage>{forceFail.error.message}</ErrorMessage>}
            </>
          ) : undefined
        }
      />
    </Tabs>
  );
}

function ImportViewTabs() {
  return (
    <TabsList aria-label="Import view">
      <TabsTrigger value="new-import">
        <Plus className="size-4" />
        New import
      </TabsTrigger>
      <TabsTrigger value="history">
        <History className="size-4" />
        Import history
      </TabsTrigger>
    </TabsList>
  );
}
function SummaryDetail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-foreground/70">{label}</dt>
      <dd className="mt-1 font-medium">{children}</dd>
    </div>
  );
}
function ErrorMessage({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
    >
      {children}
    </div>
  );
}
function LoadingState({ children }: { children: ReactNode }) {
  return (
    <output className="flex items-center gap-2 py-8 text-sm text-foreground/70">
      <Loader2 className="size-4 animate-spin" />
      {children}
    </output>
  );
}
function EmptyHistory() {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center">
      <History className="mx-auto mb-3 size-5 text-foreground/70" />
      <p className="text-sm font-medium">No imports yet</p>
      <p className="mt-1 text-sm text-foreground/70">
        Completed and running imports will appear here.
      </p>
    </div>
  );
}
function AdminRecovery({ onMark, pending }: { onMark: () => void; pending: boolean }) {
  return (
    <details className="rounded-md border p-4 text-sm">
      <summary className="cursor-pointer font-medium">Admin recovery</summary>
      <p className="mt-3 text-foreground/70">
        Mark a stuck import as failed to clear its active status. This changes the import record; it
        does not stop an executing workflow.
      </p>
      <Button className="mt-3" size="sm" variant="outline" onClick={onMark} disabled={pending}>
        Mark as failed
      </Button>
    </details>
  );
}
function ImportProgress({
  status,
  entity,
  total,
  processed,
  stopping,
  onStop,
  stopPending,
  error,
  children,
}: {
  status?: string;
  entity: string;
  total: number;
  processed: number;
  stopping: boolean;
  onStop: () => void;
  stopPending: boolean;
  error?: boolean;
  children: ReactNode;
}) {
  const percentage = Math.min(
    100,
    Math.max(0, total > 0 ? Math.round((processed / total) * 100) : 0),
  );
  const phase =
    status === "processing"
      ? `Importing ${entity}…`
      : status === "exporting"
        ? "Waiting for CDD Vault to prepare the export…"
        : status === "discovering"
          ? "Reading CDD Vault…"
          : "Starting import…";
  return (
    <section className="space-y-5 rounded-lg border p-5" aria-label="Import progress">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-medium" aria-live="polite">
            <Loader2 className="size-4 animate-spin" />
            {stopping ? "Stopping import…" : phase}
          </h2>
          <p className="mt-2 text-sm text-foreground/70">
            {stopping
              ? "The import will stop after its current work finishes. Records already imported are kept."
              : "You can leave this page and return to check progress."}
          </p>
        </div>
        {status && <Badge variant="outline">{importOutcome(status).label}</Badge>}
      </div>
      {error && (
        <ErrorMessage>
          Progress could not be refreshed. The import may still be running. We’ll keep checking.
        </ErrorMessage>
      )}
      {status === "processing" && total > 0 && (
        <div className="space-y-2">
          <div className="flex justify-between gap-3 text-sm">
            <span>
              {processed.toLocaleString()} of {total.toLocaleString()} {entity} processed
            </span>
            <span className="tabular-nums">{percentage}%</span>
          </div>
          <progress
            aria-label={`${entity} processed`}
            value={percentage}
            max={100}
            aria-valuenow={percentage}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-2 w-full appearance-none overflow-hidden rounded-full bg-muted [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
          />
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>
      <Button variant="outline" size="sm" onClick={onStop} disabled={stopPending || stopping}>
        <Square className="size-3" />
        {stopping ? "Stop requested" : "Stop import"}
      </Button>
    </section>
  );
}
