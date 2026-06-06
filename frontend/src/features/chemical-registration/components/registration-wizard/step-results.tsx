"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { AlertTriangle, Check, Copy, ExternalLink, Eye, GitMerge, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { useConfirmMerges } from "../../hooks/use-registration-wizard-api";
import type { MergeDecision } from "../../types/registration-wizard";
import { MergeCandidateCard } from "./merge-candidate-card";

// ---------------------------------------------------------------------------
// StepResults
// ---------------------------------------------------------------------------

export function StepResults() {
  const mode = useRegistrationWizard((s) => s.mode);

  if (mode === "single") return <SingleResults />;
  if (mode === "bulk") return <BulkResults />;
  return null;
}

// ---------------------------------------------------------------------------
// Single Mode — no merge candidate
// ---------------------------------------------------------------------------

function SingleSuccessCard() {
  const singleResult = useRegistrationWizard((s) => s.singleResult);
  const nextStep = useRegistrationWizard((s) => s.nextStep);

  if (!singleResult) return null;

  const action = singleResult.action ?? "";
  const regNumber = singleResult.molecule.registration_number;

  const { icon, message } = getActionDisplay(action, regNumber);

  return (
    <Card>
      <CardContent className="py-8">
        <div className="flex flex-col items-center gap-4 text-center">
          {icon}
          <div>
            <p className="text-sm font-medium">{message}</p>
            {singleResult.qc_warnings.length > 0 && (
              <div className="mt-3 space-y-1">
                {singleResult.qc_warnings.map((w, i) => (
                  <p
                    key={i}
                    className="text-xs text-yellow-500 flex items-center justify-center gap-1"
                  >
                    <AlertTriangle className="h-3 w-3" />
                    {w}
                  </p>
                ))}
              </div>
            )}
          </div>
          <Button onClick={nextStep}>Continue</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Single Mode — merge candidate
// ---------------------------------------------------------------------------

function SingleMergeReview() {
  const mergeCandidates = useRegistrationWizard((s) => s.mergeCandidates);
  const mergeDecisions = useRegistrationWizard((s) => s.mergeDecisions);
  const setMergeDecision = useRegistrationWizard((s) => s.setMergeDecision);
  const nextStep = useRegistrationWizard((s) => s.nextStep);

  const candidate = mergeCandidates[0];
  const decision = mergeDecisions[candidate.disclosure_id] ?? "confirm";

  // For single mode, use workflow_id = null (individual confirm/reject)
  const confirmMerges = useConfirmMerges(null);

  const handleConfirm = async () => {
    const decisions: MergeDecision[] = [
      { disclosure_id: candidate.disclosure_id, action: "confirm" },
    ];
    await confirmMerges.mutateAsync({ decisions });
    nextStep();
  };

  const handleReject = async () => {
    const decisions: MergeDecision[] = [
      { disclosure_id: candidate.disclosure_id, action: "reject" },
    ];
    await confirmMerges.mutateAsync({ decisions });
    nextStep();
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Merge Candidate Found</h2>
        <p className="text-sm text-muted-foreground">
          A structure match was found. Review the details and decide whether to merge.
        </p>
      </div>

      <MergeCandidateCard
        candidate={candidate}
        decision={decision}
        onDecisionChange={(d) => setMergeDecision(candidate.disclosure_id, d)}
      />

      <div className="flex items-center gap-3 border-t pt-4">
        <Button onClick={handleConfirm} disabled={confirmMerges.isPending}>
          {confirmMerges.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Merging...
            </>
          ) : (
            <>
              <GitMerge className="mr-2 h-4 w-4" />
              Confirm Merge
            </>
          )}
        </Button>
        <Button variant="outline" onClick={handleReject} disabled={confirmMerges.isPending}>
          Reject
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single Results dispatcher
// ---------------------------------------------------------------------------

function SingleResults() {
  const singleResult = useRegistrationWizard((s) => s.singleResult);
  const mergeCandidates = useRegistrationWizard((s) => s.mergeCandidates);

  if (singleResult && mergeCandidates.length === 0) {
    return <SingleSuccessCard />;
  }

  if (mergeCandidates.length === 1) {
    return <SingleMergeReview />;
  }

  // Fallback (shouldn't happen)
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        No results available.
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Bulk Mode
// ---------------------------------------------------------------------------

function BulkResults() {
  const progress = useRegistrationWizard((s) => s.progress);
  const mergeCandidates = useRegistrationWizard((s) => s.mergeCandidates);
  const mergeDecisions = useRegistrationWizard((s) => s.mergeDecisions);
  const setMergeDecision = useRegistrationWizard((s) => s.setMergeDecision);
  const confirmAllMerges = useRegistrationWizard((s) => s.confirmAllMerges);
  const rejectAllMerges = useRegistrationWizard((s) => s.rejectAllMerges);
  const workflowId = useRegistrationWizard((s) => s.workflowId);
  const nextStep = useRegistrationWizard((s) => s.nextStep);

  const confirmMergesMutation = useConfirmMerges(workflowId);

  const handleConfirmSelected = async () => {
    const decisions: MergeDecision[] = Object.entries(mergeDecisions).map(
      ([disclosureId, action]) => ({
        disclosure_id: disclosureId,
        action,
      }),
    );
    await confirmMergesMutation.mutateAsync({ decisions });
    nextStep();
  };

  if (!progress) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No progress data available.
        </CardContent>
      </Card>
    );
  }

  const mergeCount = mergeCandidates.length;
  const conflictCount = progress.conflict_count;

  return (
    <div className="space-y-6">
      {/* Summary badges row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <SummaryBadge
          icon={<Check className="h-4 w-4" />}
          count={progress.registered_count}
          label="Registered"
          color="text-emerald-500 border-emerald-500/30 bg-emerald-500/5"
        />
        <SummaryBadge
          icon={<Copy className="h-4 w-4" />}
          count={progress.duplicate_count}
          label="Deduplicated"
          color="text-blue-500 border-blue-500/30 bg-blue-500/5"
        />
        <SummaryBadge
          icon={<Eye className="h-4 w-4" />}
          count={progress.disclosed_count}
          label="Disclosed"
          color="text-violet-500 border-violet-500/30 bg-violet-500/5"
        />
        <SummaryBadge
          icon={<AlertTriangle className="h-4 w-4" />}
          count={mergeCount}
          label="Merge Candidates"
          color={
            mergeCount > 0
              ? "text-yellow-500 border-yellow-500/30 bg-yellow-500/5"
              : "text-muted-foreground border-border"
          }
          highlight={mergeCount > 0}
        />
        <SummaryBadge
          icon={<AlertTriangle className="h-4 w-4" />}
          count={conflictCount}
          label="Conflicts"
          color={
            conflictCount > 0
              ? "text-destructive border-destructive/30 bg-destructive/5"
              : "text-muted-foreground border-border"
          }
        />
      </div>

      {/* Tabs for merge candidates and conflicts */}
      <Tabs defaultValue="merge-candidates">
        <TabsList>
          <TabsTrigger value="merge-candidates">Merge Candidates ({mergeCount})</TabsTrigger>
          <TabsTrigger value="conflicts">Conflicts ({conflictCount})</TabsTrigger>
        </TabsList>

        {/* Merge candidates tab */}
        <TabsContent value="merge-candidates" className="space-y-4">
          {mergeCount === 0 ? (
            <Card>
              <CardContent className="py-6 text-center text-sm text-muted-foreground">
                No merge candidates. All compounds were processed cleanly.
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Bulk actions */}
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={confirmAllMerges}>
                  Confirm All
                </Button>
                <Button variant="outline" size="sm" onClick={rejectAllMerges}>
                  Reject All
                </Button>
              </div>

              {/* Candidate list */}
              <div className="space-y-3">
                {mergeCandidates.map((candidate) => (
                  <MergeCandidateCard
                    key={candidate.disclosure_id}
                    candidate={candidate}
                    decision={mergeDecisions[candidate.disclosure_id] ?? "confirm"}
                    onDecisionChange={(d) => setMergeDecision(candidate.disclosure_id, d)}
                    disabled={confirmMergesMutation.isPending}
                  />
                ))}
              </div>

              {/* Submit button */}
              <div className="border-t pt-4">
                <Button onClick={handleConfirmSelected} disabled={confirmMergesMutation.isPending}>
                  {confirmMergesMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    "Confirm Selected & Continue"
                  )}
                </Button>
              </div>
            </>
          )}
        </TabsContent>

        {/* Conflicts tab */}
        <TabsContent value="conflicts" className="space-y-4">
          {conflictCount === 0 ? (
            <Card>
              <CardContent className="py-6 text-center text-sm text-muted-foreground">
                No conflicts detected.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {conflictCount} conflict{conflictCount === 1 ? "" : "s"} detected
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  {conflictCount} conflict{conflictCount === 1 ? "" : "s"} detected during bulk
                  registration. Resolve them on individual compound detail pages.
                </p>
                <Button variant="outline" size="sm" asChild>
                  <Link href="/compounds?disclosure_status=conflict">
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Review Conflicts
                  </Link>
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Continue when no merge candidates to review */}
      {mergeCount === 0 && (
        <div className="flex justify-end border-t pt-4">
          <Button onClick={nextStep}>Continue to Summary</Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getActionDisplay(
  action: string,
  regNumber: string,
): { icon: React.ReactNode; message: string } {
  switch (action) {
    case "registered":
      return {
        icon: (
          <div className="rounded-full bg-emerald-500/10 p-3">
            <Check className="h-6 w-6 text-emerald-500" />
          </div>
        ),
        message: `Registered as ${regNumber}`,
      };
    case "deduplicated":
      return {
        icon: (
          <div className="rounded-full bg-blue-500/10 p-3">
            <Copy className="h-6 w-6 text-blue-500" />
          </div>
        ),
        message: `Deduplicated -- added to ${regNumber}`,
      };
    case "disclosed":
      return {
        icon: (
          <div className="rounded-full bg-violet-500/10 p-3">
            <Eye className="h-6 w-6 text-violet-500" />
          </div>
        ),
        message: `Structure applied to ${regNumber}`,
      };
    default:
      return {
        icon: (
          <div className="rounded-full bg-muted p-3">
            <Check className="h-6 w-6 text-muted-foreground" />
          </div>
        ),
        message: `Processed as ${regNumber}`,
      };
  }
}

function SummaryBadge({
  icon,
  count,
  label,
  color,
  highlight,
}: {
  icon: React.ReactNode;
  count: number;
  label: string;
  color: string;
  highlight?: boolean;
}) {
  return (
    <Card className={`border ${color}`}>
      <CardContent className="flex flex-col items-center gap-1 py-3 px-2">
        <div className="flex items-center gap-1.5">
          {icon}
          <span className="text-xl font-semibold tabular-nums">{count}</span>
        </div>
        <span className="text-xs text-center">
          {highlight ? (
            <Badge variant="outline" className="text-xs font-normal">
              {label}
            </Badge>
          ) : (
            label
          )}
        </span>
      </CardContent>
    </Card>
  );
}
