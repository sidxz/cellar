import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { UseSummaryImportWizardResult } from "../hooks/use-summary-import-wizard";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

// Mock the state hook so the component renders without a QueryClient /
// network. Each test overrides the bits it cares about.
const hookState: { value: UseSummaryImportWizardResult } = {
  value: {} as UseSummaryImportWizardResult,
};

vi.mock("../hooks/use-summary-import-wizard", () => ({
  useSummaryImportWizard: () => hookState.value,
}));

import { SummaryImportWizard } from "./summary-import-wizard";

function baseHook(
  overrides: Partial<UseSummaryImportWizardResult> = {},
): UseSummaryImportWizardResult {
  return {
    step: 1,
    file: null,
    preview: null,
    draft: { roles: {}, readoutDefByHeader: {} },
    resolvePreview: null,
    result: null,
    // mutations are only read for pending/data in the hook itself; the
    // component reads the derived flags below, so a cast is fine here.
    previewMutation: {} as UseSummaryImportWizardResult["previewMutation"],
    resolveMutation: {} as UseSummaryImportWizardResult["resolveMutation"],
    importMutation: {} as UseSummaryImportWizardResult["importMutation"],
    readoutDefOptions: [],
    canContinueMapping: false,
    canImport: false,
    isPreviewing: false,
    isResolving: false,
    isImporting: false,
    setStep: vi.fn(),
    reset: vi.fn(),
    handleOpenChange: vi.fn(),
    handleFile: vi.fn(),
    setRole: vi.fn(),
    setReadoutDef: vi.fn(),
    handleContinueToPreview: vi.fn(),
    handleImport: vi.fn(),
    ...overrides,
  };
}

function renderWizard() {
  return render(
    <SummaryImportWizard runId="run-1" protocolId="proto-1" open onOpenChange={vi.fn()} />,
  );
}

describe("SummaryImportWizard", () => {
  it("step 1 shows the upload affordance", () => {
    hookState.value = baseHook({ step: 1 });
    renderWizard();
    expect(screen.getByText(/drop a csv or xlsx here, or click to browse/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /choose file/i })).toBeInTheDocument();
  });

  it("step 2 shows the mapping grid with summary roles and disables Continue until mapping is valid", () => {
    hookState.value = baseHook({
      step: 2,
      canContinueMapping: false,
      preview: {
        headers: ["Compound", "IC50"],
        suggestions: [
          { header: "Compound", role: "compound_ref", confidence: "high" },
          { header: "IC50", role: "readout", confidence: "medium" },
        ],
        sample_rows: [],
        total_rows: 2,
      },
      draft: {
        roles: { Compound: "compound_ref", IC50: "readout" },
        readoutDefByHeader: {},
      },
      readoutDefOptions: [{ id: "rd-1", name: "IC50" }],
    });
    renderWizard();
    expect(screen.getByText("Compound")).toBeInTheDocument();
    expect(screen.getByText("IC50")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("step 3 shows the dry-run forecast and warns about unmatched compounds", () => {
    hookState.value = baseHook({
      step: 3,
      canImport: true,
      resolvePreview: {
        total_rows: 5,
        matched_compound_count: 3,
        unmatched_compound_refs: ["CPD-999", "CPD-888"],
        unmatched_batch_refs: [],
        values_to_insert: 6,
        values_to_update: 1,
        rows_skipped: 2,
        errors: [],
      },
    });
    renderWizard();
    expect(screen.getByText("3 matched")).toBeInTheDocument();
    expect(screen.getByText(/unmatched compound refs/i)).toBeInTheDocument();
    expect(screen.getByText(/CPD-999/)).toBeInTheDocument();
    expect(screen.getByText("New values")).toBeInTheDocument();
    expect(screen.getByText("Overwrites")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeEnabled();
  });

  it("step 3 disables Import when nothing will be written", () => {
    hookState.value = baseHook({
      step: 3,
      canImport: false,
      resolvePreview: {
        total_rows: 2,
        matched_compound_count: 0,
        unmatched_compound_refs: ["CPD-1"],
        unmatched_batch_refs: [],
        values_to_insert: 0,
        values_to_update: 0,
        rows_skipped: 2,
        errors: [],
      },
    });
    renderWizard();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
    expect(
      screen.getByText(/nothing to import — check your compound column mapping/i),
    ).toBeInTheDocument();
  });
});
