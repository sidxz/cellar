"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Copy,
  ExternalLink,
  Eye,
  GitMerge,
  Loader2,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { useBulkRegistrationItems } from "../../hooks/use-registration-wizard-api";
import type { BulkRegItemAction } from "../../types/registration-wizard";

// ─── Action label map ────────────────────────────────────────────────────────

const ACTION_LABELS: Record<string, string> = {
  registered: "Registered",
  deduplicated: "Deduplicated",
  disclosed: "Disclosed",
  merge_candidate: "Merge Candidate",
  conflict: "Conflict",
};

// ─── StepSummary ─────────────────────────────────────────────────────────────

export function StepSummary() {
  const mode = useRegistrationWizard((s) => s.mode);

  if (mode === "single") return <SingleSummary />;
  if (mode === "bulk") return <BulkSummary />;
  return null;
}

// ─── Single Mode Summary ─────────────────────────────────────────────────────

function SingleSummary() {
  const router = useRouter();
  const singleResult = useRegistrationWizard((s) => s.singleResult);
  const reset = useRegistrationWizard((s) => s.reset);

  if (!singleResult) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No registration result available.
        </CardContent>
      </Card>
    );
  }

  const { molecule, batch } = singleResult;
  const action = singleResult.action ?? "";
  const actionLabel = ACTION_LABELS[action] ?? action;

  function handleViewCompound() {
    router.push(`/compounds/${molecule.id}`);
  }

  function handleRegisterAnother() {
    reset();
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="h-5 w-5" />
          Compound registered successfully
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Detail rows */}
        <dl className="divide-y rounded-md border">
          <SummaryRow label="Registration Number">
            <span className="font-mono font-semibold">{molecule.registration_number}</span>
          </SummaryRow>
          <SummaryRow label="Name">{molecule.name}</SummaryRow>
          <SummaryRow label="Action">
            <ActionBadge action={action} label={actionLabel} />
          </SummaryRow>
          {batch && (
            <SummaryRow label="Batch">
              <span className="font-mono">{batch.batch_number}</span>
            </SummaryRow>
          )}
        </dl>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-3 border-t pt-4">
          <Button onClick={handleViewCompound}>
            <ExternalLink className="mr-2 h-4 w-4" />
            View Compound
          </Button>
          <Button variant="outline" onClick={handleRegisterAnother}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Register Another
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Bulk Mode Summary ───────────────────────────────────────────────────────

function BulkSummary() {
  const router = useRouter();
  const progress = useRegistrationWizard((s) => s.progress);
  const workflowId = useRegistrationWizard((s) => s.workflowId);
  const reset = useRegistrationWizard((s) => s.reset);

  if (!progress) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No bulk registration data available.
        </CardContent>
      </Card>
    );
  }

  const {
    registered_count,
    duplicate_count,
    disclosed_count,
    merge_candidate_count,
    conflict_count,
    error_count,
  } = progress;

  const hasConflicts = conflict_count > 0;

  function handleViewList() {
    router.push("/compounds");
  }

  function handleRegisterMore() {
    reset();
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-5 w-5" />
            Bulk registration complete
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Count grid */}
          <dl className="divide-y rounded-md border">
            <SummaryRow label="Registered">
              <CountBadge
                count={registered_count}
                icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                className="text-emerald-600 bg-emerald-500/10"
              />
            </SummaryRow>
            <SummaryRow label="Deduplicated">
              <CountBadge
                count={duplicate_count}
                icon={<Copy className="h-3.5 w-3.5" />}
                className="text-blue-600 bg-blue-500/10"
              />
            </SummaryRow>
            <SummaryRow label="Disclosed">
              <CountBadge
                count={disclosed_count}
                icon={<Eye className="h-3.5 w-3.5" />}
                className="text-violet-600 bg-violet-500/10"
              />
            </SummaryRow>
            <SummaryRow label="Merged">
              <CountBadge
                count={merge_candidate_count}
                icon={<GitMerge className="h-3.5 w-3.5" />}
                className="text-yellow-600 bg-yellow-500/10"
              />
            </SummaryRow>
            <SummaryRow label="Conflicts">
              <CountBadge
                count={conflict_count}
                icon={<AlertTriangle className="h-3.5 w-3.5" />}
                className={
                  hasConflicts
                    ? "text-destructive bg-destructive/10"
                    : "text-muted-foreground bg-muted"
                }
              />
            </SummaryRow>
            <SummaryRow label="Errors">
              <CountBadge
                count={error_count}
                icon={<XCircle className="h-3.5 w-3.5" />}
                className={
                  error_count > 0
                    ? "text-destructive bg-destructive/10"
                    : "text-muted-foreground bg-muted"
                }
              />
            </SummaryRow>
          </dl>

          {/* Conflict note */}
          {hasConflicts && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div>
                <span className="font-medium text-destructive">
                  {conflict_count} conflict
                  {conflict_count === 1 ? "" : "s"} require manual resolution.
                </span>{" "}
                <a
                  href="/compounds?disclosure_status=conflict"
                  className="underline underline-offset-2 text-destructive hover:text-destructive/80"
                >
                  Review on compound list
                </a>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-3 border-t pt-4">
            <Button onClick={handleViewList}>
              <ExternalLink className="mr-2 h-4 w-4" />
              View Compound List
            </Button>
            <Button variant="outline" onClick={handleRegisterMore}>
              <RotateCcw className="mr-2 h-4 w-4" />
              Register More
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Per-row results table */}
      {workflowId && (
        <BulkResultsTable
          workflowId={workflowId}
          counts={{
            all:
              registered_count +
              duplicate_count +
              disclosed_count +
              merge_candidate_count +
              conflict_count +
              error_count,
            registered: registered_count,
            deduplicated: duplicate_count,
            disclosed: disclosed_count,
            merge_candidate: merge_candidate_count,
            conflict: conflict_count,
            error: error_count,
          }}
        />
      )}
    </div>
  );
}

// ─── Per-row results table ──────────────────────────────────────────────────

type ResultsFilter = "all" | BulkRegItemAction;

const RESULTS_TABS: { value: ResultsFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "registered", label: "Registered" },
  { value: "deduplicated", label: "Deduplicated" },
  { value: "disclosed", label: "Disclosed" },
  { value: "merge_candidate", label: "Merge candidates" },
  { value: "conflict", label: "Conflicts" },
  { value: "error", label: "Errors" },
];

const PAGE_SIZE = 50;

function BulkResultsTable({
  workflowId,
  counts,
}: {
  workflowId: string;
  counts: Record<ResultsFilter, number>;
}) {
  const [tab, setTab] = useState<ResultsFilter>("all");
  const [page, setPage] = useState(0);

  const action = tab === "all" ? null : tab;
  const offset = page * PAGE_SIZE;

  const query = useBulkRegistrationItems(workflowId, action, PAGE_SIZE, offset, true);

  function changeTab(next: string) {
    setTab(next as ResultsFilter);
    setPage(0);
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Per-row results</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs value={tab} onValueChange={changeTab}>
          <TabsList className="flex-wrap h-auto">
            {RESULTS_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value} className="text-xs">
                {t.label}
                <span className="ml-1.5 rounded bg-muted px-1 text-[10px] tabular-nums">
                  {counts[t.value] ?? 0}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value={tab} className="mt-3">
            {query.isPending ? (
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading results…
              </div>
            ) : query.isError ? (
              <div className="py-8 text-center text-sm text-destructive">
                {query.error?.message ?? "Failed to load results."}
              </div>
            ) : query.data && query.data.rows.length > 0 ? (
              <>
                <div className="max-h-[420px] overflow-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-muted/80 backdrop-blur">
                      <tr className="border-b">
                        <th className="px-3 py-2 text-left font-medium w-12">#</th>
                        <th className="px-3 py-2 text-left font-medium">Action</th>
                        <th className="px-3 py-2 text-left font-medium">Compound</th>
                        <th className="px-3 py-2 text-left font-medium">Reg #</th>
                        <th className="px-3 py-2 text-left font-medium">Batch</th>
                        <th className="px-3 py-2 text-left font-medium">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {query.data.rows.map((row) => (
                        <tr
                          key={row.row_index}
                          className={`border-b last:border-b-0 ${
                            row.action === "error"
                              ? "bg-destructive/5"
                              : row.action === "conflict"
                                ? "bg-destructive/[0.03]"
                                : ""
                          }`}
                        >
                          <td className="px-3 py-1.5 text-muted-foreground">{row.row_index + 1}</td>
                          <td className="px-3 py-1.5">
                            <ActionPill action={row.action} />
                          </td>
                          <td className="px-3 py-1.5">
                            {row.molecule_id && row.molecule_name ? (
                              <a
                                href={`/compounds/${row.molecule_id}`}
                                className="text-primary hover:underline"
                              >
                                {row.molecule_name}
                              </a>
                            ) : (
                              <span className="text-muted-foreground">
                                {row.molecule_name ?? "\u2014"}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-muted-foreground">
                            {row.registration_number ?? "\u2014"}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-muted-foreground">
                            {row.batch_number ?? "\u2014"}
                          </td>
                          <td className="px-3 py-1.5 text-destructive">{row.error ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {query.data.total > PAGE_SIZE && (
                  <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      Showing {offset + 1}–
                      {Math.min(offset + query.data.rows.length, query.data.total)} of{" "}
                      {query.data.total}
                    </span>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page === 0}
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={offset + query.data.rows.length >= query.data.total}
                        onClick={() => setPage((p) => p + 1)}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="py-8 text-center text-sm text-muted-foreground">
                No rows in this category.
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function ActionPill({ action }: { action: string }) {
  const map: Record<string, { label: string; className: string }> = {
    registered: {
      label: "Registered",
      className: "text-emerald-600 bg-emerald-500/10 border-emerald-500/30",
    },
    deduplicated: {
      label: "Deduplicated",
      className: "text-blue-600 bg-blue-500/10 border-blue-500/30",
    },
    disclosed: {
      label: "Disclosed",
      className: "text-violet-600 bg-violet-500/10 border-violet-500/30",
    },
    merge_candidate: {
      label: "Merge",
      className: "text-yellow-600 bg-yellow-500/10 border-yellow-500/30",
    },
    conflict: {
      label: "Conflict",
      className: "text-destructive bg-destructive/10 border-destructive/30",
    },
    error: {
      label: "Error",
      className: "text-destructive bg-destructive/10 border-destructive/30",
    },
  };
  const cfg = map[action] ?? {
    label: action || "Unknown",
    className: "text-muted-foreground bg-muted border-border",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${cfg.className}`}
    >
      {cfg.label}
    </span>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function SummaryRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function ActionBadge({ action, label }: { action: string; label: string }) {
  const variantMap: Record<string, string> = {
    registered: "text-emerald-600 bg-emerald-500/10 border-emerald-500/30",
    deduplicated: "text-blue-600 bg-blue-500/10 border-blue-500/30",
    disclosed: "text-violet-600 bg-violet-500/10 border-violet-500/30",
    merge_candidate: "text-yellow-600 bg-yellow-500/10 border-yellow-500/30",
    conflict: "text-destructive bg-destructive/10 border-destructive/30",
  };

  const cls = variantMap[action] ?? "text-muted-foreground bg-muted border-border";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

function CountBadge({
  count,
  icon,
  className,
}: {
  count: number;
  icon: React.ReactNode;
  className: string;
}) {
  return (
    <Badge
      variant="outline"
      className={`inline-flex items-center gap-1 font-semibold tabular-nums ${className}`}
    >
      {icon}
      {count}
    </Badge>
  );
}
