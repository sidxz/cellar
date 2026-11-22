"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSubmitDisclosure } from "../../hooks/use-disclosures";
import { useMolecule } from "../../hooks/use-molecules";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import {
  useBulkRegistrationStatus,
  useStartBulkRegistration,
  useSubmitRegistration,
} from "../../hooks/use-registration-wizard-api";
import type { RegisterMoleculeInput } from "../../types";
import type { SubmitDisclosureInput } from "../../types/disclosure";
import { bulkStepIndex } from "../../types/registration-wizard";
import type { DiscloserChoice } from "../discloser-pick";
import { ProjectNames } from "./project-names";

// ---------------------------------------------------------------------------
// StepProcessing
// ---------------------------------------------------------------------------

/** The discloser pick as request fields; omitted when it is "you" and "your org". */
function discloserFields(d: DiscloserChoice): {
  disclosed_by?: string;
  disclosed_by_org_id?: string;
} {
  return {
    ...(d.userId ? { disclosed_by: d.userId } : {}),
    ...(d.orgId ? { disclosed_by_org_id: d.orgId } : {}),
  };
}

export function StepProcessing() {
  const mode = useRegistrationWizard((s) => s.mode);

  if (mode === "single") return <SingleProcessing />;
  if (mode === "bulk") return <BulkProcessing />;
  return null;
}

// ---------------------------------------------------------------------------
// Single Mode
// ---------------------------------------------------------------------------

function SingleProcessing() {
  const singleInput = useRegistrationWizard((s) => s.singleInput);
  const setSingleResult = useRegistrationWizard((s) => s.setSingleResult);
  const setMergeCandidates = useRegistrationWizard((s) => s.setMergeCandidates);
  const nextStep = useRegistrationWizard((s) => s.nextStep);
  const prevStep = useRegistrationWizard((s) => s.prevStep);

  const registerMutation = useSubmitRegistration();
  const disclosureMutation = useSubmitDisclosure();
  const moleculeQuery = useMolecule(
    singleInput.disclosureMode ? (singleInput.moleculeId ?? undefined) : undefined,
  );
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDisclosure = singleInput.disclosureMode && !!singleInput.moleculeId;
  const isSubmitting = registerMutation.isPending || disclosureMutation.isPending;

  const handleSubmit = () => {
    setConfirmed(true);
    setError(null);

    if (isDisclosure) {
      const disclosureInput: SubmitDisclosureInput = {
        molecule_id: singleInput.moleculeId!,
        disclosed_smiles: singleInput.smiles ?? "",
        auto_approve: false,
        scientist_name: singleInput.scientistName || null,
        disclosing_org_id: singleInput.disclosingOrgId || null,
        notes: singleInput.notes || null,
      };

      disclosureMutation
        .mutateAsync(disclosureInput)
        .then((outcome) => {
          const mol = moleculeQuery.data!;
          setSingleResult({
            molecule: mol,
            is_new: false,
            qc_warnings: [],
            batch_skipped: false,
            action: outcome.needs_confirmation
              ? "merge_candidate"
              : outcome.was_merged
                ? "deduplicated"
                : "disclosed",
            needs_merge_confirmation: outcome.needs_confirmation,
            matched_molecule_id: outcome.matched_molecule_id,
            disclosure_id: outcome.disclosure_request.id,
            conflict_reason: null,
          });
          if (outcome.needs_confirmation) {
            setMergeCandidates([
              {
                row_index: 0,
                molecule_id: mol.id,
                matched_molecule_id: outcome.matched_molecule_id!,
                disclosure_id: outcome.disclosure_request.id,
              },
            ]);
          }
          nextStep();
        })
        .catch((err: Error) => {
          setError(err.message ?? "Disclosure failed");
          setConfirmed(false);
        });
    } else {
      const input: RegisterMoleculeInput = {
        name: singleInput.name,
        smiles: singleInput.smiles,
        molecule_type: singleInput.moleculeType,
        external_ids: singleInput.externalIds.map((e) => ({
          identifier: e.identifier,
          identifier_type: e.identifier_type,
        })),
        ...discloserFields(singleInput.discloser),
        custom_fields: singleInput.customFields,
        project_ids: singleInput.projectIds,
      };

      registerMutation
        .mutateAsync(input)
        .then((data) => {
          setSingleResult(data);
          if (data.needs_merge_confirmation) {
            setMergeCandidates([
              {
                row_index: 0,
                molecule_id: data.molecule.id,
                matched_molecule_id: data.matched_molecule_id!,
                disclosure_id: data.disclosure_id!,
              },
            ]);
          }
          nextStep();
        })
        .catch((err: Error) => {
          setError(err.message ?? "Registration failed");
          setConfirmed(false);
        });
    }
  };

  // Submitting spinner
  if (confirmed && isSubmitting) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">
              {isDisclosure ? "Disclosing compound..." : "Registering compound..."}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error
  if (error) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive" />
            <div>
              <p className="text-sm font-medium">
                {isDisclosure ? "Disclosure failed" : "Registration failed"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{error}</p>
            </div>
            <Button variant="outline" onClick={prevStep}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Confirmation review card
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {isDisclosure ? "Confirm Disclosure" : "Confirm Registration"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border bg-muted/50 p-4 space-y-2 text-sm">
          {isDisclosure ? (
            <>
              <Row
                label="Compound"
                value={moleculeQuery.data?.name ?? singleInput.moleculeId ?? ""}
              />
              <Row label="SMILES" value={singleInput.smiles ?? ""} mono />
              {singleInput.scientistName && (
                <Row label="Scientist" value={singleInput.scientistName} />
              )}
              {singleInput.notes && <Row label="Notes" value={singleInput.notes} />}
            </>
          ) : (
            <>
              <Row label="Name" value={singleInput.name} />
              {singleInput.smiles ? (
                <Row label="SMILES" value={singleInput.smiles} mono />
              ) : (
                <Row label="Structure" value="Undisclosed" />
              )}
              <Row label="Type" value={singleInput.moleculeType} />
              {singleInput.externalIds.length > 0 && (
                <Row
                  label="Identifiers"
                  value={singleInput.externalIds.map((e) => e.identifier).join(", ")}
                />
              )}
              {singleInput.projectIds.length > 0 && (
                <Row label="Projects" value={<ProjectNames ids={singleInput.projectIds} />} />
              )}
            </>
          )}
        </div>

        <div className="flex justify-between pt-2">
          <Button variant="outline" onClick={prevStep}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={handleSubmit}>
            {isDisclosure ? "Confirm & Disclose" : "Confirm & Register"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex gap-2">
      <span className="text-muted-foreground w-24 shrink-0">{label}:</span>
      <span className={mono ? "font-mono text-xs break-all" : ""}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bulk Mode
// ---------------------------------------------------------------------------

function BulkProcessing() {
  const bulkInput = useRegistrationWizard((s) => s.bulkInput);
  const bulkMapping = useRegistrationWizard((s) => s.bulkMapping);
  const workflowId = useRegistrationWizard((s) => s.workflowId);
  const setWorkflowId = useRegistrationWizard((s) => s.setWorkflowId);
  const setProgress = useRegistrationWizard((s) => s.setProgress);
  const setMergeCandidates = useRegistrationWizard((s) => s.setMergeCandidates);
  const setCurrentStep = useRegistrationWizard((s) => s.setCurrentStep);
  const nextStep = useRegistrationWizard((s) => s.nextStep);
  const prevStep = useRegistrationWizard((s) => s.prevStep);

  const startMutation = useStartBulkRegistration();
  const hasStarted = useRef(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Kick off the bulk job on mount
  // biome-ignore lint/correctness/useExhaustiveDependencies: kick off the bulk job once on mount (guarded by hasStarted ref); the captured bulkInput/startMutation must not re-trigger the job.
  useEffect(() => {
    if (workflowId || hasStarted.current || !bulkInput.file) return;
    hasStarted.current = true;

    startMutation
      .mutateAsync({
        file: bulkInput.file,
        file_format: bulkInput.fileFormat,
        ...discloserFields(bulkInput.discloser),
        create_batch_on_duplicate: bulkInput.createBatchOnDuplicate,
        project_ids: bulkInput.projectIds,
        column_mapping: bulkMapping ? JSON.stringify(bulkMapping) : null,
      })
      .then((data) => {
        setWorkflowId(data.workflow_id);
      })
      .catch((err: Error) => {
        setStartError(err.message ?? "Failed to start bulk registration");
      });
  }, []);

  // Poll for progress.
  const statusQuery = useBulkRegistrationStatus(workflowId, !!workflowId);
  const progress = statusQuery.data;

  // Mirror the latest progress into the store so the Summary step (which reads
  // `s.progress`) has the final counts after we advance. Without this the
  // summary renders "No bulk registration data available" — and, on the
  // collection-import return path, the "Add to collection" CTA never appears.
  // Polling stops on completed/failed, so this settles on the final value.
  useEffect(() => {
    if (progress) setProgress(progress);
  }, [progress, setProgress]);

  // Auto-advance when complete
  const hasAdvanced = useRef(false);
  // biome-ignore lint/correctness/useExhaustiveDependencies: auto-advance keys only on `progress` (guarded by hasAdvanced ref); the store actions (setMergeCandidates/nextStep/setCurrentStep) are stable and intentionally omitted.
  useEffect(() => {
    if (!progress || hasAdvanced.current) return;

    if (progress.status === "completed") {
      hasAdvanced.current = true;
      if (progress.merge_candidates.length > 0) {
        setMergeCandidates(progress.merge_candidates);
        nextStep();
      } else {
        // Skip results step, jump to summary.
        setCurrentStep(bulkStepIndex("Summary"));
      }
    }
  }, [progress]);

  // Error states
  if (statusQuery.isError) {
    return (
      <Card>
        <CardContent className="space-y-3 py-8">
          <h2 className="font-medium">Could not refresh registration</h2>
          <p role="alert" className="text-sm text-destructive">
            {statusQuery.error?.message ??
              "The registration could not be loaded. It may still be running."}
          </p>
          <Button variant="outline" onClick={() => statusQuery.refetch()}>
            Try again
          </Button>
          <p className="text-sm text-foreground/70">
            This page’s address lets you return to the registration without uploading the file
            again.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (startError || progress?.status === "failed") {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive" />
            <div>
              <p className="text-sm font-medium">Bulk registration failed</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {startError ?? "The bulk registration job encountered an error."}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => (workflowId ? setCurrentStep(bulkStepIndex("Summary")) : prevStep())}
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              {workflowId ? "View recorded results" : "Edit registration"}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Progress display
  const processed = progress
    ? progress.registered_count +
      progress.duplicate_count +
      progress.disclosed_count +
      progress.merge_candidate_count +
      progress.conflict_count +
      progress.error_count
    : 0;
  const total = progress?.total_count ?? 0;
  const progressPercent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base" aria-live="polite">
          Registering compounds
        </CardTitle>
        <p className="text-sm text-foreground/70">
          Registration continues in the background. This page’s address lets you return after
          navigating away or reloading.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Progress bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {total > 0
                ? `${processed.toLocaleString()} of ${total.toLocaleString()} rows processed`
                : "Preparing registration…"}
            </span>
            <span>{progressPercent}%</span>
          </div>
          {total > 0 && (
            <progress
              value={progressPercent}
              max={100}
              aria-label="Registration progress"
              className="h-2 w-full appearance-none overflow-hidden rounded-full bg-muted [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
            />
          )}
        </div>

        {/* Running counts */}
        {progress && (
          <div className="flex flex-wrap gap-3 text-sm">
            <CountBadge label="Registered" count={progress.registered_count} />
            <CountBadge label="Matched existing" count={progress.duplicate_count} />
            <CountBadge label="Structures added" count={progress.disclosed_count} />
            <CountBadge
              label="Merge candidates"
              count={progress.merge_candidate_count}
              variant="warning"
            />
            <CountBadge label="Conflicts" count={progress.conflict_count} variant="warning" />
            <CountBadge label="Errors" count={progress.error_count} variant="destructive" />
          </div>
        )}

        {!progress && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Starting registration…
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// CountBadge helper
// ---------------------------------------------------------------------------

function CountBadge({
  label,
  count,
  variant,
}: {
  label: string;
  count: number;
  variant?: "warning" | "destructive";
}) {
  const color =
    variant === "destructive"
      ? "text-destructive"
      : variant === "warning"
        ? "text-yellow-500"
        : "text-foreground";

  return (
    <div className="flex items-center gap-1.5">
      <Badge variant="outline" className={count > 0 ? color : "opacity-50"}>
        {count}
      </Badge>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}
