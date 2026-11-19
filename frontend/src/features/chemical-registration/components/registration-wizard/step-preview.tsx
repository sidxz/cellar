"use client";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { usePreviewBulkRegistration } from "../../hooks/use-registration-wizard-api";
import { PreviewTable } from "../preview-table";
import { ProjectNames } from "./project-names";

// ---------------------------------------------------------------------------
// StepPreview — parse-only preview between Input and Processing
// ---------------------------------------------------------------------------

export function StepPreview() {
  const bulkInput = useRegistrationWizard((s) => s.bulkInput);
  const bulkPreview = useRegistrationWizard((s) => s.bulkPreview);
  const bulkMapping = useRegistrationWizard((s) => s.bulkMapping);
  const setBulkPreview = useRegistrationWizard((s) => s.setBulkPreview);
  const nextStep = useRegistrationWizard((s) => s.nextStep);
  const prevStep = useRegistrationWizard((s) => s.prevStep);

  const previewMutation = usePreviewBulkRegistration();
  const hasRequested = useRef(false);

  // Kick off preview on mount when no data yet
  // biome-ignore lint/correctness/useExhaustiveDependencies: kick off the preview once on mount (guarded by hasRequested ref); the captured bulkInput/previewMutation are intentionally not re-subscribed.
  useEffect(() => {
    if (hasRequested.current || bulkPreview || !bulkInput.file) return;
    hasRequested.current = true;
    previewMutation
      .mutateAsync({ file: bulkInput.file, mapping: bulkMapping })
      .then((data) => setBulkPreview(data))
      .catch(() => {
        // Error surfaced via mutation state below.
      });
  }, []);

  if (!bulkInput.file) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground text-sm">
          No file selected. Go back and choose one.
        </CardContent>
      </Card>
    );
  }

  if (previewMutation.isPending && !bulkPreview) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Parsing {bulkInput.file.name}…</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (previewMutation.isError) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive" />
            <div>
              <p className="text-sm font-medium">Could not parse file</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {previewMutation.error?.message ?? "Parser returned an unknown error."}
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

  if (!bulkPreview) return null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Preview</h2>
          <p className="text-sm text-muted-foreground">
            What each row will do. Nothing is saved until you register.
          </p>
          {bulkInput.projectIds.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Will be added to: <ProjectNames ids={bulkInput.projectIds} />
            </p>
          )}
        </div>
      </div>

      <PreviewTable
        items={bulkPreview.items}
        createBatchOnDuplicate={bulkInput.createBatchOnDuplicate}
        footer={({ counts, answered, importable }) => (
          <div className="flex items-center justify-between border-t pt-4">
            <Button variant="outline" onClick={prevStep}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
            <div className="flex items-center gap-3">
              {answered && (
                <span className="text-sm text-muted-foreground tabular-nums">
                  {counts.newCompounds} new compound{counts.newCompounds === 1 ? "" : "s"} ·{" "}
                  {counts.newBatches} new batch{counts.newBatches === 1 ? "" : "es"}
                </span>
              )}
              <Button onClick={nextStep} disabled={!importable}>
                Register
              </Button>
            </div>
          </div>
        )}
      />
    </div>
  );
}
