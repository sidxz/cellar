"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { formatDateTime } from "@/shared/lib/format-date";
import { AlertTriangle, CheckCircle2, Download, Square, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import type {
  CddMoleculeImportStatus,
  CddMoleculeImportSummary,
} from "../hooks/use-cdd-molecule-import";
import type { CddPlateImportStatus, CddPlateImportSummary } from "../hooks/use-cdd-plate-import";
import {
  describeImportIssue,
  importOutcome,
  importScopeLabel,
} from "../lib/cdd-import-presentation";

type MoleculeRun = CddMoleculeImportStatus | CddMoleculeImportSummary;
type PlateRun = CddPlateImportStatus | CddPlateImportSummary;

export function ImportStatusBadge({
  status,
  reason,
  errors = 0,
}: { status: string; reason?: string | null; errors?: number }) {
  const outcome = importOutcome(status, reason, errors);
  return <Badge variant={outcome.tone}>{outcome.label}</Badge>;
}

export function OutcomeNotice({
  status,
  reason,
  errors,
  children,
}: {
  status: string;
  reason?: string | null;
  errors: number;
  children: ReactNode;
}) {
  const outcome = importOutcome(status, reason, errors);
  const styles = {
    success: "border-emerald-500/30 bg-emerald-500/5",
    partial: "border-amber-500/40 bg-amber-500/5",
    failed: "border-destructive/30 bg-destructive/5",
    stopped: "border-border bg-muted/30",
    active: "border-border bg-muted/30",
  };
  const Icon =
    outcome.kind === "success"
      ? CheckCircle2
      : outcome.kind === "failed"
        ? XCircle
        : outcome.kind === "stopped"
          ? Square
          : AlertTriangle;
  const colors = {
    success: "text-emerald-600",
    partial: "text-amber-600",
    failed: "text-destructive",
    stopped: "text-foreground/70",
    active: "text-foreground/70",
  };
  return (
    // biome-ignore lint/a11y/useSemanticElements: this live region contains a structured outcome and actions, rather than a form output.
    <div
      role="status"
      className={`flex items-start gap-3 rounded-lg border p-4 ${styles[outcome.kind]}`}
    >
      <Icon className={`mt-0.5 size-5 shrink-0 ${colors[outcome.kind]}`} aria-hidden="true" />
      <div className="min-w-0 space-y-2 text-sm">
        <p className="font-medium">{outcome.label}</p>
        {children}
      </div>
    </div>
  );
}

export function ReportStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border bg-background p-3">
      <p className="text-xl font-semibold tabular-nums">{value.toLocaleString()}</p>
      <p className="mt-1 text-sm text-foreground/70">{label}</p>
    </div>
  );
}

function downloadReport(name: string, lines: string[]) {
  const url = URL.createObjectURL(
    new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function RunMetadata({
  run,
  organizationName,
}: { run: MoleculeRun | PlateRun; organizationName?: string }) {
  const saved = "submitted_at" in run ? run : undefined;
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
      {saved && (
        <>
          <div>
            <dt className="text-foreground/70">Started</dt>
            <dd className="mt-1">{formatDateTime(saved.submitted_at)}</dd>
          </div>
          <div>
            <dt className="text-foreground/70">Finished</dt>
            <dd className="mt-1">
              {saved.completed_at ? formatDateTime(saved.completed_at) : "In progress"}
            </dd>
          </div>
          <div>
            <dt className="text-foreground/70">CDD vault</dt>
            <dd className="mt-1">{saved.cdd_vault_id}</dd>
          </div>
        </>
      )}
      {"import_mode" in run && (
        <>
          <div>
            <dt className="text-foreground/70">Import scope</dt>
            <dd className="mt-1">{importScopeLabel(run.import_mode)}</dd>
          </div>
          <div>
            <dt className="text-foreground/70">Originating organization</dt>
            <dd className="mt-1">{organizationName ?? "Not available"}</dd>
          </div>
          <div>
            <dt className="text-foreground/70">Molecule limit</dt>
            <dd className="mt-1">{run.max_molecules?.toLocaleString() ?? "No recorded limit"}</dd>
          </div>
        </>
      )}
    </dl>
  );
}

export function MoleculeImportReport({
  run,
  onClose,
  organizationName,
  recovery,
}: {
  run: MoleculeRun | null;
  onClose: () => void;
  organizationName?: string;
  recovery?: ReactNode;
}) {
  const report = run?.report;
  const issues = report?.problem_lines ?? [];
  const issueCount = (report?.problems ?? 0) + (report?.values_skipped ?? 0);
  const id = run && ("id" in run ? run.id : run.import_id);
  return (
    <Dialog
      open={!!run}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Compound import report</DialogTitle>
          <DialogDescription>
            Imported records, matched records, and values that need attention.
          </DialogDescription>
        </DialogHeader>
        {run && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <ImportStatusBadge
                status={run.status}
                reason={run.failure_reason}
                errors={run.error_count}
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  downloadReport(`cdd-import-${id}.txt`, [
                    "CDD Vault compound import",
                    `Status: ${importOutcome(run.status, run.failure_reason, run.error_count).label}`,
                    `Reason: ${run.failure_reason ?? "—"}`,
                    `Compounds added: ${report?.compounds_added ?? run.registered_count}`,
                    `Compounds matched: ${report?.compounds_matched ?? run.duplicate_count}`,
                    `Batches added: ${report?.batches_created ?? 0}`,
                    `Batches matched: ${report?.batches_matched ?? 0}`,
                    `Identifiers added: ${report?.ids_added ?? 0}`,
                    `Values skipped: ${report?.values_skipped ?? 0}`,
                    `Molecules with errors: ${run.error_count}`,
                    `Total molecules: ${run.total_count}`,
                    "",
                    ...issues,
                  ])
                }
              >
                <Download className="size-4" />
                Download report
              </Button>
            </div>
            <RunMetadata run={run} organizationName={organizationName} />
            {run.status === "failed" && !run.failure_reason && (
              <p className="text-sm text-foreground/70">
                This import stopped before finishing. A failure reason was not saved. Resume it if
                available, or start a new import.
              </p>
            )}
            {run.failure_reason && (
              <OutcomeNotice
                status={run.status}
                reason={run.failure_reason}
                errors={run.error_count}
              >
                <p className="break-words">
                  {importOutcome(run.status, run.failure_reason).kind === "stopped"
                    ? "The import was stopped at your request. Records already imported have been kept."
                    : run.failure_reason}
                </p>
              </OutcomeNotice>
            )}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <ReportStat
                label="Compounds added"
                value={report?.compounds_added ?? run.registered_count}
              />
              <ReportStat
                label="Compounds matched"
                value={report?.compounds_matched ?? run.duplicate_count}
              />
              <ReportStat label="Batches added" value={report?.batches_created ?? 0} />
              <ReportStat label="Batches matched" value={report?.batches_matched ?? 0} />
              <ReportStat label="Identifiers added" value={report?.ids_added ?? 0} />
              <ReportStat label="Values skipped" value={report?.values_skipped ?? 0} />
            </div>
            {"selected_names" in run && run.selected_names?.length ? (
              <details className="rounded-md border p-3 text-sm">
                <summary className="cursor-pointer font-medium">
                  Selected names ({run.selected_names.length.toLocaleString()})
                </summary>
                <p className="mt-2 whitespace-pre-wrap break-words font-mono text-xs">
                  {run.selected_names.join("\n")}
                </p>
              </details>
            ) : null}
            <section className="space-y-3" aria-label="Import issues">
              <h3 className="text-sm font-medium">Import issues ({issueCount.toLocaleString()})</h3>
              {issues.length ? (
                <>
                  <p className="text-sm text-foreground/70">
                    Review these records before retrying. Expand an issue to see the original
                    diagnostic.
                  </p>
                  <ul className="space-y-2">
                    {issues.map((line, index) => {
                      const issue = describeImportIssue(line);
                      return (
                        <li key={`${index}-${line}`} className="rounded-md border p-3 text-sm">
                          <details>
                            <summary className="cursor-pointer break-words">
                              <span className="font-medium">{issue.name}</span>
                              <span className="ml-2">{issue.reason}</span>
                            </summary>
                            <p className="mt-2">{issue.next}</p>
                            <p className="mt-3 text-xs font-medium text-foreground/70">
                              Technical details
                            </p>
                            <pre className="mt-1 whitespace-pre-wrap break-all text-xs text-foreground/70">
                              {line}
                            </pre>
                          </details>
                        </li>
                      );
                    })}
                  </ul>
                  {issueCount > issues.length && (
                    <p className="text-sm text-foreground/70">
                      Showing the first {issues.length.toLocaleString()} recorded issues.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-foreground/70">
                  {run.error_count > 0
                    ? `${run.error_count.toLocaleString()} molecules could not be imported. Detailed diagnostics were not saved for this import.`
                    : "No row-level issues were recorded."}
                </p>
              )}
            </section>
            {recovery}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function PlateImportReport({
  run,
  onClose,
  recovery,
}: { run: PlateRun | null; onClose: () => void; recovery?: ReactNode }) {
  return (
    <Dialog
      open={!!run}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Plate import report</DialogTitle>
          <DialogDescription>
            Imported plates and the outcome of matching wells to batches.
          </DialogDescription>
        </DialogHeader>
        {run && (
          <>
            <ImportStatusBadge
              status={run.status}
              reason={run.failure_reason}
              errors={run.plates_error}
            />
            <RunMetadata run={run} />
            {run.failure_reason && (
              <OutcomeNotice
                status={run.status}
                reason={run.failure_reason}
                errors={run.plates_error}
              >
                <p>
                  {importOutcome(run.status, run.failure_reason).kind === "stopped"
                    ? "The import was stopped at your request. Plates already imported have been kept."
                    : run.failure_reason}
                </p>
              </OutcomeNotice>
            )}
            <div className="grid grid-cols-2 gap-3">
              <ReportStat label="Plates added" value={run.plates_registered} />
              <ReportStat label="Plates matched" value={run.plates_duplicate} />
              <ReportStat label="Plate errors" value={run.plates_error} />
              <ReportStat label="Wells matched to batches" value={run.wells_mapped} />
              <ReportStat label="Wells without a batch match" value={run.wells_unresolved} />
              <ReportStat label="Total plates" value={run.total_count} />
            </div>
            {run.wells_unresolved > 0 && (
              <p className="text-sm">
                Some wells could not be matched. Import the corresponding compounds and batches,
                then review the plate import.
              </p>
            )}
            {recovery}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
