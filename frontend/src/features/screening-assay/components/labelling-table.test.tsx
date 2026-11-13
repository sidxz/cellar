import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { LabellingRow } from "../lib/labelling-rows";

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

// The pickers query the API; their own behaviour is covered where they live.
vi.mock("@/features/inventory/components/molecule-selector", () => ({
  MoleculeSelector: () => <span>compound picker</span>,
}));
vi.mock("@/features/inventory/components/batch-selector", () => ({
  BatchSelector: () => <span>batch picker</span>,
}));

import { LabellingTable, type LabellingTableProps } from "./labelling-table";

const rows: LabellingRow[] = [
  {
    key: "a",
    positionLabel: "Position 1",
    used: true,
    label: "ABC-0000001",
    note: "",
    wellType: "reference",
    moleculeId: "m1",
    moleculeName: "ABC-0000001",
    batchId: "b1",
    batchNumber: "B-1",
    dose: "10",
  },
  {
    key: "b",
    positionLabel: "Position 2",
    used: true,
    label: "",
    note: "",
    wellType: "sample",
    moleculeId: "m2",
    moleculeName: "ABC-0000002",
    batchId: null,
    dose: "",
  },
  {
    key: "c",
    positionLabel: "Position 3",
    used: true,
    label: "",
    note: "",
    wellType: "sample",
    moleculeId: null,
    moleculeName: null,
    batchId: null,
    dose: "",
  },
];

function renderTable(props: Partial<LabellingTableProps> = {}) {
  const onUpdate = vi.fn();
  const onSetRole = vi.fn();
  render(
    <LabellingTable
      rows={rows}
      doseUnit="µM"
      onUpdate={onUpdate}
      onSetRole={onSetRole}
      showUse
      problem={null}
      {...props}
    />,
  );
  return { onUpdate, onSetRole };
}

describe("LabellingTable", () => {
  it("renders one row per row with its position label and the dose unit in the header", () => {
    renderTable();
    for (const label of ["Position 1", "Position 2", "Position 3"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Conc. (µM)")).toBeInTheDocument();
    expect(screen.getByText(/Concentration is in µM/)).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(4);
  });

  it("hides the Use column and Mark unused when showUse is false", () => {
    renderTable({ showUse: false });
    expect(screen.queryByRole("columnheader", { name: "Use" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark unused" })).not.toBeInTheDocument();
    expect(screen.queryByText("Used")).not.toBeInTheDocument();
  });

  it("shows the Use column and Mark unused when showUse is true", () => {
    renderTable();
    expect(screen.getByRole("columnheader", { name: "Use" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark unused" })).toBeInTheDocument();
  });

  it("makes role, compound, batch and concentration read-only and shows the sentence when calculatedLocked is set", () => {
    renderTable({ showUse: false, calculatedLocked: "These cannot change now." });
    expect(screen.getByText("These cannot change now.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /^role for/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: /role for selected rows/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^concentration for/i })).not.toBeInTheDocument();
    expect(screen.queryByText("compound picker")).not.toBeInTheDocument();
    expect(screen.queryByText("batch picker")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /change compound for/i })).not.toBeInTheDocument();
    // The values are still shown, as text.
    expect(screen.getByText("Reference")).toBeInTheDocument();
    expect(screen.getByText("B-1")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    // Label and note stay editable.
    for (const input of [
      ...screen.getAllByRole("textbox", { name: /^label for/i }),
      ...screen.getAllByRole("textbox", { name: /^note for/i }),
    ]) {
      expect(input).toBeEnabled();
    }
  });

  it("marks a row with a compound and no batch as not chosen", () => {
    renderTable();
    expect(screen.getAllByText("not chosen")).toHaveLength(1);
  });

  it("applies a role to the selected rows through onSetRole", () => {
    const { onSetRole } = renderTable();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Position 1" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Position 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply to selected" }));
    expect(onSetRole).toHaveBeenCalledWith(new Set(["a", "c"]), "sample");
  });

  it("reports an edit by the row's key", () => {
    const { onUpdate } = renderTable();
    fireEvent.change(screen.getByRole("textbox", { name: "Note for Position 2" }), {
      target: { value: "bubble" },
    });
    expect(onUpdate).toHaveBeenCalledWith("b", { note: "bubble" });
  });

  it("shows the wizard's badges from hints and the problem line", () => {
    renderTable({
      hints: new Map([
        ["a", { noMatch: false, suggestedId: "m1" }],
        ["c", { noMatch: true, suggestedId: null }],
      ]),
      problem: "Position 3: the concentration must be a number, 0 or more.",
    });
    expect(screen.getByText("matched")).toBeInTheDocument();
    expect(screen.getByText("No match")).toBeInTheDocument();
    expect(
      screen.getByText(
        "To continue, correct Position 3: the concentration must be a number, 0 or more.",
      ),
    ).toBeInTheDocument();
  });
});
