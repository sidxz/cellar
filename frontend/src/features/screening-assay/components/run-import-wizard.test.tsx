import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { PreviewRunFileResponse } from "../hooks/use-run-import";
import type { UseRunImportWizardResult } from "../hooks/use-run-import-wizard";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither.
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

const hookState: { value: UseRunImportWizardResult } = {
  value: {} as UseRunImportWizardResult,
};

vi.mock("../hooks/use-run-import-wizard", () => ({
  useRunImportWizard: () => hookState.value,
}));

import { RunImportWizard } from "./run-import-wizard";

const PREVIEW: PreviewRunFileResponse = {
  preview_id: "pv-1",
  headers: ["Well", "Control State", "Raw Data"],
  suggestions: [
    { header: "Well", role: "well", confidence: "high" },
    { header: "Control State", role: "well_role", confidence: "high" },
    { header: "Raw Data", role: "readout", confidence: "high" },
  ],
  sample_rows: [],
  plates: [
    {
      plate_name: "P1",
      plate_format: "384",
      well_count: 384,
      sample_count: 352,
      positive_count: 16,
      negative_count: 16,
      reference_count: 0,
      blank_count: 0,
      roles_from: 'the file\'s "Control State" column',
    },
  ],
  matched_batch_count: 0,
  expires_in_seconds: 60,
  total_rows: 384,
  matched_compound_count: 0,
  rows_skipped: 0,
  values_to_insert: 384,
  values_to_update: 0,
  will_create_plates: 1,
  will_create_wells: 384,
};

function baseHook(overrides: Partial<UseRunImportWizardResult> = {}): UseRunImportWizardResult {
  return {
    step: 3,
    file: null,
    preview: PREVIEW,
    draft: {
      roles: { Well: "well", "Control State": "well_role", "Raw Data": "readout" },
      readoutDefByHeader: { "Raw Data": "rd-1" },
      acknowledgedLowConfidence: false,
    },
    setDraft: vi.fn(),
    appliedTemplate: null,
    saveAsTemplate: false,
    templateName: "",
    autoCreateUnmatchedBatches: false,
    compoundPicks: {},
    acknowledgedSwappedControls: false,
    previewMutation: {} as UseRunImportWizardResult["previewMutation"],
    repreviewMutation: { isPending: false } as UseRunImportWizardResult["repreviewMutation"],
    importMutation: { isPending: false } as UseRunImportWizardResult["importMutation"],
    createTemplate: {} as UseRunImportWizardResult["createTemplate"],
    readoutDefs: [{ id: "rd-1", name: "Raw Data" }],
    protocol: undefined,
    wellHeader: "Well",
    lowConfidenceHeaders: [],
    readoutHeaders: ["Raw Data"],
    canContinueStep2: true,
    setStep: vi.fn(),
    setAppliedTemplate: vi.fn(),
    setSaveAsTemplate: vi.fn(),
    setTemplateName: vi.fn(),
    setAutoCreateUnmatchedBatches: vi.fn(),
    setCompoundPicks: vi.fn(),
    setAcknowledgedSwappedControls: vi.fn(),
    reset: vi.fn(),
    handleOpenChange: vi.fn(),
    handleFile: vi.fn(),
    handleSetRole: vi.fn(),
    handleSetReadoutDef: vi.fn(),
    handleContinueFromMapping: vi.fn(),
    buildMapping: vi.fn(),
    handleSubmit: vi.fn(),
    ...overrides,
  };
}

function renderWizard() {
  return render(<RunImportWizard runId="run-1" protocolId="proto-1" open onOpenChange={vi.fn()} />);
}

describe("RunImportWizard", () => {
  it("offers Well Role on the mapping step and shows it for a suggested Control State column", () => {
    const setRole = vi.fn();
    hookState.value = baseHook({ step: 2, handleSetRole: setRole });
    renderWizard();
    const row = screen.getByText("Control State").closest("tr") as HTMLElement;
    const select = within(row).getByRole("combobox");
    expect(select).toHaveTextContent("Well Role");

    const wellRow = screen.getAllByText("Well")[0].closest("tr") as HTMLElement;
    fireEvent.click(within(wellRow).getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: "Well Role" }));
    expect(setRole).toHaveBeenCalledWith("Well", "well_role");
  });

  it("shows each plate's well counts by role and where the roles come from", () => {
    hookState.value = baseHook({
      preview: {
        ...PREVIEW,
        warnings: [
          'Control roles from the file\'s "Control State" column differ from the protocol default "NadD 384" on 32 wells.',
        ],
      },
    });
    renderWizard();
    const table = screen.getByRole("table");
    for (const header of ["Samples", "Positive", "Negative", "Reference", "Blank", "Roles from"]) {
      expect(within(table).getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    const cells = within(within(table).getAllByRole("row")[1])
      .getAllByRole("cell")
      .map((c) => c.textContent);
    expect(cells).toEqual([
      "P1",
      "384",
      "384",
      "352",
      "16",
      "16",
      "0",
      "0",
      'the file\'s "Control State" column',
    ]);
    expect(
      screen.getByText(/differ from the protocol default "NadD 384" on 32 wells/),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeEnabled();
  });

  it("holds Import until swapped-looking controls are acknowledged", () => {
    const acknowledge = vi.fn();
    const swapped = {
      ...PREVIEW,
      swapped_controls: [
        "Plate P1: the full-effect controls (negative controls, mean 0.95) read higher than the no-effect controls (positive controls, mean 0.07); this protocol expects the full effect to lower the signal.",
      ],
    };
    hookState.value = baseHook({ preview: swapped, setAcknowledgedSwappedControls: acknowledge });
    const { unmount } = renderWizard();
    expect(screen.getByText(/^Plate P1: the full-effect controls/)).toBeVisible();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
    // The acknowledgement says what importing anyway does to the values.
    const ack = screen.getByRole("checkbox", {
      name: /import anyway.*inactive wells read near 100 % and hits near 0 %/i,
    });
    fireEvent.click(ack);
    expect(acknowledge).toHaveBeenCalledWith(true);
    unmount();

    hookState.value = baseHook({ preview: swapped, acknowledgedSwappedControls: true });
    renderWizard();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeEnabled();
  });

  it("tells a file-role problem apart from missing protocol setup", () => {
    hookState.value = baseHook({
      preview: {
        ...PREVIEW,
        validation_errors: ['Unknown values in the "Control State" column: "vehicle".'],
      },
    });
    renderWizard();
    expect(screen.getByText(/unknown values in the "control state" column/i)).toBeVisible();
    expect(screen.queryByText(/protocol setup needed/i)).not.toBeInTheDocument();
    expect(screen.getByText(/set the column to ignore/i)).toBeVisible();
  });

  it("counts controls from the file on the confirm step", () => {
    hookState.value = baseHook({
      step: 4,
      importMutation: {
        isPending: false,
        data: {
          total_rows: 384,
          plates_created: 1,
          wells_created: 384,
          values_inserted: 384,
          values_updated: 0,
          matched_compound_count: 0,
          rows_skipped: 0,
          controls_from_template: 0,
          controls_from_file: 32,
          controls_unclassified: 0,
        },
      } as unknown as UseRunImportWizardResult["importMutation"],
    });
    renderWizard();
    expect(screen.getByText(/32 controls from the file/)).toBeInTheDocument();
  });
});
