"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, AlertTriangle } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Badge } from "@/shared/components/ui/badge";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import {
  useSubmitRegistration,
  useStartBulkRegistration,
  useBulkRegistrationStatus,
} from "../../hooks/use-registration-wizard-api";
import { useSubmitDisclosure } from "../../hooks/use-disclosures";
import { useMolecule } from "../../hooks/use-molecules";
import type { RegisterMoleculeInput } from "../../types";
import type { SubmitDisclosureInput } from "../../types/disclosure";

// ---------------------------------------------------------------------------
// StepProcessing
// ---------------------------------------------------------------------------

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
    singleInput.disclosureMode ? singleInput.moleculeId ?? undefined : undefined
  );
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDisclosure = singleInput.disclosureMode && !!singleInput.moleculeId;
  const isSubmitting =
    registerMutation.isPending || disclosureMutation.isPending;

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
        originating_org_id: singleInput.originatingOrgId!,
        custom_fields: singleInput.customFields,
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
              <Row label="Compound" value={moleculeQuery.data?.name ?? singleInput.moleculeId ?? ""} />
              <Row label="SMILES" value={singleInput.smiles ?? ""} mono />
              {singleInput.scientistName && (
                <Row label="Scientist" value={singleInput.scientistName} />
              )}
              {singleInput.notes && (
                <Row label="Notes" value={singleInput.notes} />
              )}
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

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
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
  useEffect(() => {
    if (hasStarted.current || !bulkInput.file) return;
    hasStarted.current = true;

    startMutation
      .mutateAsync({
        file: bulkInput.file,
        file_format: bulkInput.fileFormat,
        originating_org_id: bulkInput.originatingOrgId,
        create_batch_on_duplicate: bulkInput.createBatchOnDuplicate,
      })
      .then((data) => {
        setWorkflowId(data.workflow_id);
      })
      .catch((err: Error) => {
        setStartError(err.message ?? "Failed to start bulk registration");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  useEffect(() => {
    if (!progress || hasAdvanced.current) return;

    if (progress.status === "completed") {
      hasAdvanced.current = true;
      if (progress.merge_candidates.length > 0) {
        setMergeCandidates(progress.merge_candidates);
        nextStep();
      } else {
        // Skip results step, jump to summary.
        // Bulk steps: 0=Input, 1=Preview, 2=Processing, 3=Results, 4=Summary
        setCurrentStep(4);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress]);

  // Error states
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
            <Button variant="outline" onClick={prevStep}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Progress display
  const chunksProcessed = progress?.chunks_processed ?? 0;
  const chunksTotal = progress?.chunks_total ?? 0;
  const progressPercent =
    chunksTotal > 0 ? Math.round((chunksProcessed / chunksTotal) * 100) : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Processing Compounds</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Progress bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Chunk {chunksProcessed} of {chunksTotal || "..."}
            </span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Running counts */}
        {progress && (
          <div className="flex flex-wrap gap-3 text-sm">
            <CountBadge label="Registered" count={progress.registered_count} />
            <CountBadge label="Deduplicated" count={progress.duplicate_count} />
            <CountBadge label="Disclosed" count={progress.disclosed_count} />
            <CountBadge
              label="Merge Candidates"
              count={progress.merge_candidate_count}
              variant="warning"
            />
            <CountBadge
              label="Conflicts"
              count={progress.conflict_count}
              variant="warning"
            />
            <CountBadge
              label="Errors"
              count={progress.error_count}
              variant="destructive"
            />
          </div>
        )}

        {!progress && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Starting job...
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
