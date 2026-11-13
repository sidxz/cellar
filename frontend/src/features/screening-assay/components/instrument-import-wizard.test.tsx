import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { UseInstrumentImportWizardResult } from "../hooks/use-instrument-import-wizard";
import { draftFromPreview } from "../lib/instrument-labelling";
import type { InstrumentImportResult, InstrumentPreview, LayoutFile } from "../types";

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

type ResolveOptions = { onSuccess?: (f: LayoutFile) => void; onError?: (e: unknown) => void };
const resolve = vi.hoisted(() => ({
  mutate: vi.fn<(vars: { file: File }, opts?: ResolveOptions) => void>(),
  isPending: false,
}));
vi.mock("../hooks/use-layout-file", () => ({ useResolveLayoutFile: () => resolve }));
const download = vi.hoisted(() => ({ saveText: vi.fn() }));
vi.mock("@/shared/lib/api/download", () => download);
const formats = vi.hoisted(() => ({
  value: { data: undefined, isLoading: false, isError: false } as {
    data: { formats: { id: string; label: string; hint: string }[] } | undefined;
    isLoading: boolean;
    isError: boolean;
  },
}));
vi.mock("../hooks/use-instrument-import", () => ({
  useInstrumentFileFormats: () => formats.value,
}));
const FORMATS = {
  formats: [
    { id: "a", label: "Format A", hint: "Export format A" },
    { id: "b", label: "Format B", hint: "Export format B" },
  ],
};

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
        registration_number: "REG-0001",
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
  stored_file_name: null,
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
    replacePositions: vi.fn(),
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
    expect(screen.getByText("Recognized")).toBeInTheDocument();
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

  it("step 1 takes a file of any type and leaves the format check to the API", async () => {
    const handleFile = vi.fn();
    hookState.value = baseHook({ step: 1, handleFile });
    const { container } = renderWizard();
    expect(screen.queryByText(".xlsx")).not.toBeInTheDocument();
    const input = container.ownerDocument.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.getAttribute("accept") ?? "").toBe("");
    const other = new File(["a,b"], "export.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [other] } });
    await waitFor(() => expect(handleFile).toHaveBeenCalledWith(other));
  });

  it("step 2 says which position blocks Continue and why", () => {
    const draft = draftFromPreview(preview);
    draft.positions[1] = { ...draft.positions[1], dose: "abc" };
    hookState.value = withPreview(2, { draft, canImport: false });
    renderWizard();
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
    expect(
      screen.getByText(
        "To continue, correct Position 2: the concentration must be a number, 0 or more.",
      ),
    ).toBeInTheDocument();
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
        attachment_warning: "The file could not be attached. Upload it on the Files tab.",
      },
    });
    renderWizard();
    expect(screen.getAllByText(/the file could not be attached/i)).toHaveLength(1);
    expect(screen.getByText(/the data is imported/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /done/i })).toBeInTheDocument();
  });

  it("the result step names the stored file when it was renamed", () => {
    hookState.value = withPreview(4, { result: { ...result, stored_file_name: "run (2).xlsx" } });
    renderWizard();
    expect(
      screen.getByText(/the original file is on the files tab as run \(2\)\.xlsx/i),
    ).toBeInTheDocument();
  });

  it("offers a template with a Use column", () => {
    download.saveText.mockReset();
    hookState.value = withPreview(2);
    renderWizard();
    fireEvent.click(screen.getByRole("button", { name: "Download template" }));
    const [csv, name] = download.saveText.mock.calls[0] as [string, string];
    expect(csv.split("\r\n")[0]).toBe(
      "\uFEFFPosition,Label,Role,Compound,Batch,Concentration (µM),Note,Use",
    );
    expect(csv.split("\r\n")[1]).toBe("Position 1,ABC-0000001,Sample,REG-0001,B-1,,,Yes");
    expect(name.endsWith(".csv")).toBe(true);
  });

  it("puts the rows filled from a file in the draft", () => {
    const replacePositions = vi.fn();
    hookState.value = withPreview(2, { replacePositions });
    const { container } = renderWizard();
    resolve.mutate.mockImplementation((_vars, opts) =>
      opts?.onSuccess?.({
        rows: [
          {
            position: "Position 3",
            label: null,
            note: null,
            well_type: null,
            dose: 5,
            use: false,
            compound: null,
            problems: [],
          },
        ],
        unrecognised_columns: [],
        calculated_columns_ignored: false,
      }),
    );
    const input = container.ownerDocument.querySelector(
      'input[type="file"][accept=".csv,.xlsx"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "layout.csv")] } });
    const filled = replacePositions.mock.calls[0][0];
    expect(filled[2]).toMatchObject({ row: 1, column: 3, dose: "5", used: false });
    expect(
      screen.getByText(
        "Filled 1 position from layout.csv. Nothing is saved until you press Import.",
      ),
    ).toBeInTheDocument();
  });

  it("step 1 lists the supported instrument files before a file is chosen", () => {
    formats.value = { data: FORMATS, isLoading: false, isError: false };
    hookState.value = baseHook({ step: 1 });
    renderWizard();
    const block = screen.getByRole("region", { name: "Supported instrument files" });
    expect(within(block).getByText("Format A")).toBeInTheDocument();
    expect(within(block).getByText("Export format A")).toBeInTheDocument();
    expect(within(block).getByText("Format B")).toBeInTheDocument();
    expect(within(block).getByText("Export format B")).toBeInTheDocument();
  });

  it("step 1 still lists the supported files beside a refusal", () => {
    formats.value = { data: FORMATS, isLoading: false, isError: false };
    hookState.value = baseHook({ step: 1, error: "Unrecognized instrument file." });
    renderWizard();
    expect(screen.getByText("Unrecognized instrument file.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Supported instrument files" })).toBeInTheDocument();
  });

  it("step 1 shows nothing about supported files while loading or when the request fails", () => {
    formats.value = { data: undefined, isLoading: true, isError: false };
    hookState.value = baseHook({ step: 1 });
    const { unmount } = renderWizard();
    expect(screen.queryByText("Supported instrument files")).not.toBeInTheDocument();
    unmount();
    formats.value = { data: undefined, isLoading: false, isError: true };
    renderWizard();
    expect(screen.queryByText("Supported instrument files")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose file" })).toBeEnabled();
  });
});
