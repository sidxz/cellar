import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { LabellingRow } from "../lib/labelling-rows";
import type { LayoutFile } from "../types";

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

type ResolveOptions = { onSuccess?: (f: LayoutFile) => void; onError?: (e: unknown) => void };
const resolve = vi.hoisted(() => ({
  mutate: vi.fn<(vars: { file: File }, opts?: ResolveOptions) => void>(),
  isPending: false,
}));
vi.mock("../hooks/use-layout-file", () => ({ useResolveLayoutFile: () => resolve }));
const download = vi.hoisted(() => ({ saveText: vi.fn() }));
vi.mock("@/shared/lib/api/download", () => download);

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
    moleculeRef: "REG-0001",
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
    moleculeRef: "REG-0002",
    batchId: null,
    batchNumber: null,
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
    moleculeRef: null,
    batchId: null,
    batchNumber: null,
    dose: "",
  },
];

function renderTable(props: Partial<LabellingTableProps<LabellingRow>> = {}) {
  const onUpdate = vi.fn();
  const onSetRole = vi.fn();
  const onReplaceRows = vi.fn();
  const view = render(
    <LabellingTable
      rows={rows}
      doseUnit="µM"
      onUpdate={onUpdate}
      onSetRole={onSetRole}
      onReplaceRows={onReplaceRows}
      runId="run-1"
      templateName="labelling.csv"
      showUse
      problem={null}
      {...props}
    />,
  );
  return { onUpdate, onSetRole, onReplaceRows, container: view.container };
}

const noValues = {
  label: null,
  note: null,
  well_type: null,
  dose: null,
  use: null,
  compound: null,
};

/** Choose a file in Fill from file and answer with the given outcome. */
function fillFromFile(container: HTMLElement, answer: (opts: ResolveOptions) => void) {
  resolve.mutate.mockReset();
  resolve.mutate.mockImplementation((_vars, opts) => answer(opts ?? {}));
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["Position"], "layout.csv", { type: "text/csv" });
  fireEvent.change(input, { target: { files: [file] } });
  expect(resolve.mutate).toHaveBeenCalledWith({ file }, expect.anything());
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

  it("Download template saves the table's rows as CSV under the given name", () => {
    download.saveText.mockReset();
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Download template" }));
    expect(download.saveText).toHaveBeenCalledWith(
      expect.stringContaining("Position,Label,Role,Compound,Batch"),
      "labelling.csv",
    );
    const csv = download.saveText.mock.calls[0][0] as string;
    expect(csv).toContain("Position 1,ABC-0000001,Reference,REG-0001,B-1,10,,Yes");
  });

  it("Fill from file accepts CSV and spreadsheet files", () => {
    const { container } = renderTable();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.getAttribute("accept")).toBe(".csv,.xlsx");
    expect(screen.getByRole("button", { name: "Fill from file" })).toBeEnabled();
  });

  it("Fill from file hands the filled rows to onReplaceRows and says nothing is saved yet", () => {
    const { container, onReplaceRows } = renderTable();
    fillFromFile(container, (o) =>
      o.onSuccess?.({
        rows: [{ position: "Position 2", ...noValues, dose: 12.5, problems: [] }],
        unrecognised_columns: [],
        calculated_columns_ignored: false,
      }),
    );
    expect(onReplaceRows).toHaveBeenCalledTimes(1);
    const filled = onReplaceRows.mock.calls[0][0] as LabellingRow[];
    expect(filled[1]).toEqual({ ...rows[1], dose: "12.5" });
    expect(
      screen.getByText(
        "Filled 1 position from layout.csv. Nothing is saved until you press Import.",
      ),
    ).toBeInTheDocument();
  });

  it("says Save, not Import, where positions cannot be added or removed", () => {
    const { container } = renderTable({ showUse: false });
    fillFromFile(container, (o) =>
      o.onSuccess?.({
        rows: [{ position: "Position 2", ...noValues, label: "y", problems: [] }],
        unrecognised_columns: [],
        calculated_columns_ignored: false,
      }),
    );
    expect(
      screen.getByText("Filled 1 position from layout.csv. Nothing is saved until you press Save."),
    ).toBeInTheDocument();
  });

  it("lists the file's problems above the table, each naming its position", () => {
    const { container } = renderTable();
    fillFromFile(container, (o) =>
      o.onSuccess?.({
        rows: [
          { position: "Position 1", ...noValues, label: "y", problems: ["Use must be Yes or No"] },
          { position: "Position 9", ...noValues, problems: [] },
        ],
        unrecognised_columns: ["Plate"],
        calculated_columns_ignored: false,
      }),
    );
    const heading = screen.getByText("2 rows need attention");
    const notice = heading.parentElement as HTMLElement;
    expect(within(notice).getByText("Position 1: Use must be Yes or No")).toBeInTheDocument();
    expect(
      within(notice).getByText("Position 9: not a position in this table; skipped"),
    ).toBeInTheDocument();
    expect(screen.getByText("Columns not recognised and ignored: Plate")).toBeInTheDocument();
    // Above the table.
    const table = screen.getByRole("table");
    expect(heading.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the API's reason when the file cannot be read and leaves the table alone", () => {
    const { container, onReplaceRows } = renderTable();
    fillFromFile(container, (o) =>
      o.onError?.(new Error("API error: 422 — The file has no Position column")),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("The file has no Position column");
    expect(onReplaceRows).not.toHaveBeenCalled();
  });

  it("a new file replaces the previous file's messages", () => {
    const { container } = renderTable();
    fillFromFile(container, (o) => o.onError?.(new Error("API error: 422 — File is empty")));
    fillFromFile(container, (o) =>
      o.onSuccess?.({
        rows: [{ position: "Position 2", ...noValues, label: "y", problems: [] }],
        unrecognised_columns: [],
        calculated_columns_ignored: false,
      }),
    );
    expect(screen.queryByText("File is empty")).not.toBeInTheDocument();
    expect(screen.getByText(/Filled 1 position from layout.csv/)).toBeInTheDocument();
  });

  it("reads Reading… and is disabled while the file is read", () => {
    resolve.isPending = true;
    try {
      renderTable();
      expect(screen.getByRole("button", { name: "Reading…" })).toBeDisabled();
    } finally {
      resolve.isPending = false;
    }
  });
});
