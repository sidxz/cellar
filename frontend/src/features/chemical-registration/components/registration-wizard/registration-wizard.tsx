"use client";

import { useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { StepInput } from "./step-input";
import { StepProcessing } from "./step-processing";
import { StepResults } from "./step-results";
import { StepBatch } from "./step-batch";
import { StepSummary } from "./step-summary";
import type { WizardMode } from "../../types/registration-wizard";

// ─── Step definitions per mode ──────────────────────────────────────────────

const SINGLE_STEPS = ["Input", "Processing", "Results", "Batch", "Summary"];
const BULK_STEPS = ["Input", "Processing", "Results", "Summary"];

function getSteps(mode: WizardMode | null): string[] {
  if (mode === "single") return SINGLE_STEPS;
  if (mode === "bulk") return BULK_STEPS;
  return [];
}

// ─── Step indicator ─────────────────────────────────────────────────────────

function StepIndicator({
  steps,
  currentStep,
}: {
  steps: string[];
  currentStep: number;
}) {
  if (steps.length === 0) return null;

  return (
    <div className="flex items-center gap-2" role="navigation" aria-label="Wizard steps">
      {steps.map((name, index) => {
        const isActive = index === currentStep;
        const isCompleted = index < currentStep;

        return (
          <div key={name} className="flex items-center gap-2">
            {index > 0 && (
              <div
                className={`h-px w-6 ${
                  isCompleted ? "bg-primary" : "bg-border"
                }`}
              />
            )}
            <Badge
              variant={isActive ? "default" : isCompleted ? "secondary" : "outline"}
              className={`text-xs font-medium ${
                isActive ? "" : isCompleted ? "opacity-80" : "opacity-50"
              }`}
            >
              {index + 1}. {name}
            </Badge>
          </div>
        );
      })}
    </div>
  );
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

  const steps = useMemo(() => getSteps(mode), [mode]);

  // ─── URL param initialization ───────────────────────────────────────────
  useEffect(() => {
    const modeParam = searchParams.get("mode");
    if (modeParam === "bulk") {
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
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Unsaved changes warning ────────────────────────────────────────────
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Warn if user has selected a mode (i.e. started the wizard)
      if (mode !== null) {
        e.preventDefault();
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [mode]);

  // ─── Cleanup on unmount ─────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      reset();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Render step content ────────────────────────────────────────────────
  function renderStep() {
    // No mode selected yet — show mode selection
    if (mode === null) {
      return <StepInput />;
    }

    // Step 0 is always the input step
    if (currentStep === 0) {
      return <StepInput />;
    }

    // Step 1 = Processing
    if (currentStep === 1) {
      return <StepProcessing />;
    }

    // Step 2 = Results
    if (currentStep === 2) {
      return <StepResults />;
    }

    // Single mode: step 3 = Batch, step 4 = Summary
    // Bulk mode:   step 3 = Summary (no batch step)
    if (mode === "single") {
      if (currentStep === 3) return <StepBatch />;
      if (currentStep === 4) return <StepSummary />;
    }

    if (mode === "bulk") {
      if (currentStep === 3) return <StepSummary />;
    }

    return null;
  }

  // Processing step disables back
  const isProcessingStep = mode !== null && currentStep === 1;
  const canGoBack = mode !== null && currentStep > 0 && !isProcessingStep;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
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
          aria-label="Go back"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {mode === null
              ? "Register Compounds"
              : mode === "bulk"
                ? "Bulk Registration"
                : "Register Compound"}
          </h1>
          {mode !== null && (
            <p className="text-sm text-muted-foreground mt-1">
              {mode === "single"
                ? "Register a single chemical compound"
                : "Upload multiple compounds from a file"}
            </p>
          )}
        </div>
      </div>

      {/* Step indicator */}
      {mode !== null && (
        <StepIndicator steps={steps} currentStep={currentStep} />
      )}

      {/* Step content */}
      {renderStep()}
    </div>
  );
}
