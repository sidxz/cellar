import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { UseInstrumentImportWizardResult } from "../hooks/use-instrument-import-wizard";
import { draftFromPreview } from "../lib/instrument-labelling";
import type { InstrumentImportResult, InstrumentPreview } from "../types";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

const hookState: { value: UseInstrumentImportWizardResult } = {
  value: {} as UseInstrumentImportWizardResult,
};
vi.mock("../hooks/use-instrument-import-wizard", () => ({
  useInstrumentImportWizard: () => hookState.value,
}));
// The pickers query the API; their own behaviour is covered where they live.
vi.mock("@/features/inventory/components/molecule-selector", () => ({
  MoleculeSelector: () => <span>compound picker</span>,
}));
vi.mock("@/features/inventory/components/batch-selector", () => ({
  BatchSelector: () => <span>batch picker</span>,
}));

import { InstrumentImportWizard } from "./instrument-import-wizard";

const preview: InstrumentPreview = {
  reader: "reader-1",
  reader_label: "Reader one raw export",
  holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3 positions" },
  dose_unit: "uM",
  positions: [
    {
      row: 1,
      column: 1,
      position_label: "Position 1",
      label: "ABC-0000001",
      suggestion: {
        molecule_id: "m1",
        molecule_name: "ABC-0000001",
        batches: [{ batch_id: "b1", batch_number: "B-1" }],
        batch_id: "b1",
      },
    },
    { row: 1, column: 2, position_label: "Position 2", label: "", suggestion: null },
    { row: 1, column: 3, position_label: "Position 3", label: "", suggestion: null },
  ],
  channels: [{ key: "ratio", label: "Channel A", x_unit: "°C", y_unit: null, x_label: null }],
  series: [
    {
      channel: "ratio",
      kind: "transition",
      ordinal: 1,
      label: "Transition 1",
      unit: "°C",
      count: 3,
      suggested_readout_definition_id: "r1",
    },
  ],
  readouts: [
    { id: "r1", name: "Transition 1", unit: "°C" },
    { id: "r2", name: "Percent", unit: "%" },
  ],
  settings: { "Start temperature": "25" },
  warnings: ["Reported value 'Onset 1' names channel 'other', which the file has no curves for"],
};

const result: InstrumentImportResult = {
  reader: "reader-1",
  positions_created: 3,
  curves_created: 3,
  values_inserted: 3,
  warnings: [],
  compute_warning: null,
  file_attached: true,
  attachment_id: "att-1",
  attachment_warning: null,
};

function baseHook(
  overrides: Partial<UseInstrumentImportWizardResult> = {},
): UseInstrumentImportWizardResult {
  return {
    step: 1,
    file: null,
    preview: null,
    draft: { positions: [], readoutBySeries: {} },
    result: null,
    error: null,
    isPreviewing: false,
    isImporting: false,
    canImport: false,
    handleFile: vi.fn(),
    updatePosition: vi.fn(),
    setRole: vi.fn(),
    setSeriesReadout: vi.fn(),
    setStep: vi.fn(),
    handleImport: vi.fn(),
    handleOpenChange: vi.fn(),
    ...overrides,
  };
}

function withPreview(
  step: 1 | 2 | 3 | 4,
  overrides: Partial<UseInstrumentImportWizardResult> = {},
) {
  return baseHook({
    step,
    file: new File(["x"], "run.xlsx"),
    preview,
    draft: draftFromPreview(preview),
    canImport: true,
    ...overrides,
  });
}

function renderWizard() {
  return render(<InstrumentImportWizard runId="run-1" open onOpenChange={vi.fn()} />);
}

describe("InstrumentImportWizard", () => {
  it("step 1 shows the recognised format and the holder line from the API", () => {
    hookState.value = withPreview(1);
    renderWizard();
    expect(screen.getByText("Recognised")).toBeInTheDocument();
    expect(screen.getByText("Reader one raw export")).toBeInTheDocument();
    expect(screen.getByText("Holder of 3 positions")).toBeInTheDocument();
    expect(screen.getByText("Start temperature")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continue/i })).toBeEnabled();
  });

  it("step 1 shows the API's reason when the file is refused", () => {
    hookState.value = baseHook({ step: 1, error: "File is larger than 20 MB" });
    renderWizard();
    expect(screen.getByText("File is larger than 20 MB")).toBeInTheDocument();
  });

  it("step 2 renders one row per position with the API's position label and the dose unit", () => {
    hookState.value = withPreview(2);
    renderWizard();
    for (const label of ["Position 1", "Position 2", "Position 3"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Conc. (µM)")).toBeInTheDocument();
    expect(screen.getByText(/Concentration is in µM/)).toBeInTheDocument();
    expect(screen.getByText("ABC-0000001", { selector: "span" })).toBeInTheDocument();
  });

  it("step 2 shows a file with blank labels as editable empty rows", () => {
    hookState.value = withPreview(2);
    renderWizard();
    const labels = screen.getAllByRole("textbox", { name: /^label for/i });
    expect(labels).toHaveLength(3);
    expect(labels[1]).toHaveValue("");
    expect(labels[1]).toBeEnabled();
  });

  it("step 2 has a note field per position", () => {
    hookState.value = withPreview(2);
    renderWizard();
    expect(screen.getAllByRole("textbox", { name: /^note for/i })).toHaveLength(3);
  });

  it("step 3 shows a different-unit readout as disabled", async () => {
    hookState.value = withPreview(3);
    renderWizard();
    expect(screen.getByText(/which the file has no curves for/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("combobox", { name: /readout for transition 1/i }));
    const option = await screen.findByRole("option", { name: /percent.*different unit/i });
    expect(option).toHaveAttribute("aria-disabled", "true");
  });

  it("step 4 disables Import when canImport is false and shows the warnings", () => {
    hookState.value = withPreview(4, { canImport: false });
    renderWizard();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
    expect(screen.getByText(/2 positions have no batch/i)).toBeInTheDocument();
    expect(screen.getByText(/which the file has no curves for/)).toBeInTheDocument();
    const used = screen.getByText("positions used").parentElement as HTMLElement;
    expect(within(used).getByText("3")).toBeInTheDocument();
  });

  it("the result step says whether the file was attached", () => {
    hookState.value = withPreview(4, { result });
    const { unmount } = renderWizard();
    expect(screen.getByText(/the original file is on the files tab/i)).toBeInTheDocument();
    unmount();

    hookState.value = withPreview(4, {
      result: {
        ...result,
        file_attached: false,
        attachment_id: null,
        attachment_warning: "storage unavailable",
      },
    });
    renderWizard();
    expect(screen.getByText(/the file could not be attached/i)).toBeInTheDocument();
    expect(screen.getByText(/storage unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /done/i })).toBeInTheDocument();
  });
});
