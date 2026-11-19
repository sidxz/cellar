"use client";

import { Button } from "@/shared/components/ui/button";
import { WizardStepIndicator } from "@/shared/components/wizard-step-indicator";
import { ArrowLeft } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { useCollectionImportHandoff } from "../../hooks/use-collection-import-handoff";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { type WizardMode, bulkStepIndex } from "../../types/registration-wizard";
import { StepBatch } from "./step-batch";
import { StepInput } from "./step-input";
import { StepMapping } from "./step-mapping";
import { StepPreview } from "./step-preview";
import { StepProcessing } from "./step-processing";
import { StepResults } from "./step-results";
import { StepSummary } from "./step-summary";

// ─── Step definitions per mode ──────────────────────────────────────────────

const SINGLE_STEPS = ["Input", "Processing", "Results", "Batch", "Summary"];

function getSteps(mode: WizardMode | null): string[] {
  if (mode === "single") return SINGLE_STEPS;
  if (mode === "bulk") return ["Upload", "Match columns", "Review & register", "Results"];
  return [];
}

// ─── Wizard shell ───────────────────────────────────────────────────────────

export function RegistrationWizard() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const mode = useRegistrationWizard((s) => s.mode);
  const currentStep = useRegistrationWizard((s) => s.currentStep);
  const setMode = useRegistrationWizard((s) => s.setMode);
  const prevStep = useRegistrationWizard((s) => s.prevStep);
  const updateSingleInput = useRegistrationWizard((s) => s.updateSingleInput);
  const reset = useRegistrationWizard((s) => s.reset);
  const workflowId = useRegistrationWizard((s) => s.workflowId);

  const steps = useMemo(() => getSteps(mode), [mode]);

  // ─── Collection-import handoff (CSV stash → bulkInput) ──────────────────
  // When the user arrives via ?from_collection_import=<preview_id>, fetch
  // the stashed unregistered rows and inject them as a CSV file into the
  // wizard's bulkInput. Also forces bulk mode.
  useCollectionImportHandoff();

  // ─── URL param initialization ───────────────────────────────────────────
  // biome-ignore lint/correctness/useExhaustiveDependencies: read the initial mode/disclose URL params once on mount; later searchParams changes should not re-seed the wizard.
  useEffect(() => {
    const workflow = searchParams.get("workflow_id");
    if (workflow && /^[A-Za-z0-9_-]{1,255}$/.test(workflow)) {
      const store = useRegistrationWizard.getState();
      if (store.workflowId !== workflow) {
        reset();
        setMode("bulk");
        store.setWorkflowId(workflow);
        store.setCurrentStep(bulkStepIndex("Processing"));
      }
      return;
    }
    const modeParam = searchParams.get("mode");
    if (modeParam === "bulk" && !useRegistrationWizard.getState().workflowId) {
      setMode("bulk");
    }

    const discloseId = searchParams.get("disclose");
    if (discloseId) {
      setMode("single");
      updateSingleInput({
        disclosureMode: true,
        moleculeId: discloseId,
      });
    }
  }, []);

  // A server-side registration can be revisited without keeping the File in memory.
  useEffect(() => {
    if (mode !== "bulk" || !workflowId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("mode", "bulk");
    url.searchParams.set("workflow_id", workflowId);
    window.history.replaceState(null, "", url);
  }, [mode, workflowId]);

  // ─── Unsaved changes warning ────────────────────────────────────────────
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Warn if user has selected a mode (i.e. started the wizard)
      if (mode !== null && !workflowId) {
        e.preventDefault();
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [mode, workflowId]);

  // Preserve bulk drafts and active job references across in-app navigation.
  // biome-ignore lint/correctness/useExhaustiveDependencies: cleanup reads the current store on unmount; reset is stable.
  useEffect(() => {
    return () => {
      const state = useRegistrationWizard.getState();
      if (state.mode === "bulk") return;
      reset();
    };
  }, []);

  // ─── Render step content ────────────────────────────────────────────────
  // Single steps:  0=Input  1=Processing  2=Results  3=Batch    4=Summary
  // Bulk steps:    0=Input  1=Match columns  2=Preview  3=Processing  4=Results  5=Summary
  function renderStep() {
    // No mode selected yet — show mode selection
    if (mode === null) {
      return <StepInput />;
    }

    if (currentStep === 0) return <StepInput />;

    if (mode === "single") {
      if (currentStep === 1) return <StepProcessing />;
      if (currentStep === 2) return <StepResults />;
      if (currentStep === 3) return <StepBatch />;
      if (currentStep === 4) return <StepSummary />;
    }

    if (mode === "bulk") {
      if (currentStep === 1) return <StepMapping />;
      if (currentStep === 2) return <StepPreview />;
      if (currentStep === 3) return <StepProcessing />;
      if (currentStep === 4) return <StepResults />;
      if (currentStep === 5) return <StepSummary />;
    }

    return null;
  }

  // Processing step disables back. Step indices differ by mode.
  const processingStepIndex = mode === "bulk" ? bulkStepIndex("Processing") : 1;
  const isProcessingStep = mode !== null && currentStep === processingStepIndex;
  const canGoBack =
    mode !== null &&
    currentStep > 0 &&
    !isProcessingStep &&
    (mode !== "bulk" || currentStep < bulkStepIndex("Processing"));
  const visibleStep = mode === "bulk" ? Math.min(currentStep + 1, 4) : currentStep + 1;

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => {
            if (canGoBack) {
              prevStep();
            } else {
              router.push("/compounds");
            }
          }}
          aria-label={canGoBack ? "Previous step" : "Back to compounds"}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {mode === null
              ? "Register Compounds"
              : mode === "bulk"
                ? "Register compounds from a file"
                : "Register Compound"}
          </h1>
          {mode !== null && (
            <p className="mt-1 text-sm text-foreground/70">
              {mode === "single"
                ? "Register a single chemical compound"
                : "Upload your file, match its columns, and review the expected changes."}
            </p>
          )}
        </div>
        {mode === "bulk" && !workflowId && (
          <Button
            className="ml-auto"
            variant="ghost"
            size="sm"
            onClick={() => {
              reset();
              const url = new URL(window.location.href);
              url.searchParams.delete("mode");
              url.searchParams.delete("from_collection_import");
              window.history.replaceState(null, "", url);
            }}
          >
            Change method
          </Button>
        )}
      </div>

      {/* Step indicator */}
      {mode !== null && (
        <WizardStepIndicator
          steps={steps}
          current={visibleStep}
          className="flex-wrap gap-y-3 rounded-lg border bg-muted/20 p-4"
        />
      )}

      {/* Step content */}
      {renderStep()}
    </div>
  );
}
