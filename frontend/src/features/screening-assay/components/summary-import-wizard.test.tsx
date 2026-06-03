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
    result: null,
    isDragging: false,
    fileInputRef: { current: null },
    // mutations are only read for pending/data in the hook itself; the
    // component reads the derived flags below, so a cast is fine here.
    previewMutation: {} as UseSummaryImportWizardResult["previewMutation"],
    importMutation: {} as UseSummaryImportWizardResult["importMutation"],
    readoutDefOptions: [],
    canContinueMapping: false,
    isPreviewing: false,
    isImporting: false,
    setStep: vi.fn(),
    setIsDragging: vi.fn(),
    reset: vi.fn(),
    handleOpenChange: vi.fn(),
    handleFile: vi.fn(),
    handleDrop: vi.fn(),
    setRole: vi.fn(),
    setReadoutDef: vi.fn(),
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
  it("renders the dialog with the title when open", () => {
    hookState.value = baseHook();
    renderWizard();
    expect(screen.getByText("Import Summary Results")).toBeInTheDocument();
  });

  it("step 1 shows the upload affordance", () => {
    hookState.value = baseHook({ step: 1 });
    renderWizard();
    expect(screen.getByText(/drop a csv or xlsx here, or click to browse/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /choose file/i })).toBeInTheDocument();
  });

  it("step 2 shows the mapping grid with summary roles and disables Import until mapping is valid", () => {
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
    expect(screen.getByRole("button", { name: /import/i })).toBeDisabled();
  });

  it("step 3 shows the result summary counts", () => {
    hookState.value = baseHook({
      step: 3,
      result: {
        rows_processed: 10,
        values_inserted: 8,
        values_updated: 1,
        rows_skipped: 1,
        errors: [],
      },
    });
    renderWizard();
    expect(screen.getByText(/import complete/i)).toBeInTheDocument();
    expect(screen.getByText("Inserted")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /done/i })).toBeInTheDocument();
  });
});
