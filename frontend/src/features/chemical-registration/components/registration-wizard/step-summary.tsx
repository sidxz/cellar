"use client";

import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  RotateCcw,
  Copy,
  Eye,
  GitMerge,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Badge } from "@/shared/components/ui/badge";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";

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

  const { molecule, action, batch } = singleResult;
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
            <span className="font-mono font-semibold">
              {molecule.registration_number}
            </span>
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

  const cls =
    variantMap[action] ?? "text-muted-foreground bg-muted border-border";

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
