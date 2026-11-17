import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { PositionLabelMatchesResponse } from "@/shared/lib/api/model";
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
type MatchOptions = {
  onSuccess?: (m: PositionLabelMatchesResponse) => void;
  onError?: (e: unknown) => void;
};
const match = vi.hoisted(() => ({
  mutate: vi.fn<(vars: { labels: string[] }, opts?: MatchOptions) => void>(),
  isPending: false,
}));
vi.mock("../hooks/use-layout-file", () => ({
  useResolveLayoutFile: () => resolve,
  useResolvePositionLabels: () => match,
}));
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
    expect(screen.getAllByText("No batch selected")).toHaveLength(1);
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
    expect(screen.getByText("Matched")).toBeInTheDocument();
    expect(screen.getByText("No match")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Correct the following before continuing: Position 3: the concentration must be a number, 0 or more.",
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
    const heading = screen.getByText("2 issues need attention");
    const notice = heading.parentElement as HTMLElement;
    expect(within(notice).getByText("Position 1: Use must be Yes or No")).toBeInTheDocument();
    expect(
      within(notice).getByText("Position 9: not a position in this table; skipped"),
    ).toBeInTheDocument();
    expect(screen.getByText("Columns not recognized and ignored: Plate")).toBeInTheDocument();
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

describe("LabellingTable label and batch wording", () => {
  it("says No label for an unused row without one, and No label in file in the wizard", () => {
    renderTable({ rows: [rows[0], { ...rows[2], used: false }] });
    expect(screen.getByText("No label")).toBeInTheDocument();
    renderTable({ rows: [rows[1]] });
    expect(screen.getByRole("textbox", { name: "Label for Position 2" })).toHaveAttribute(
      "placeholder",
      "No label in file",
    );
  });

  it("shows Batch unavailable, not an identifier, for a read-only batch without a number", () => {
    renderTable({
      rows: [{ ...rows[0], batchNumber: null }],
      showUse: false,
      calculatedLocked: "Locked.",
    });
    expect(screen.getByText("Batch unavailable")).toBeInTheDocument();
    expect(screen.queryByText("b1")).not.toBeInTheDocument();
  });
});

describe("LabellingTable Match from labels", () => {
  const blank = rows[2];
  /** Position 1 keeps its compound; 2 to 5 have a label and none; 6 has neither. */
  const labelled: LabellingRow[] = [
    rows[0],
    { ...blank, key: "p2", positionLabel: "Position 2", label: "SACC-0000002" },
    { ...blank, key: "p3", positionLabel: "Position 3", label: "DMSO" },
    { ...blank, key: "p4", positionLabel: "Position 4", label: "SACC-0000004" },
    { ...blank, key: "p5", positionLabel: "Position 5", label: "160 CoA" },
    { ...blank, key: "p6", positionLabel: "Position 6" },
  ];
  const oneBatch = {
    molecule_id: "m2",
    molecule_name: "Compound two",
    registration_number: "REG-0002",
    batch_id: "b2",
    batch_number: "B-2",
    needs_batch_choice: false,
  };
  const severalBatches = {
    molecule_id: "m4",
    molecule_name: "Compound four",
    registration_number: "REG-0004",
    batch_id: null,
    batch_number: null,
    needs_batch_choice: true,
  };
  const answer: PositionLabelMatchesResponse = {
    matches: [
      { label: "SACC-0000002", compound: oneBatch },
      { label: "DMSO", compound: null },
      { label: "SACC-0000004", compound: severalBatches },
      { label: "160 CoA", compound: null },
    ],
  };
  const button = () => screen.getByRole("button", { name: "Match from labels" });

  /** Press Match from labels and answer with the given outcome. */
  function matchFromLabels(respond: (opts: MatchOptions) => void) {
    match.mutate.mockReset();
    match.mutate.mockImplementation((_vars, opts) => respond(opts ?? {}));
    fireEvent.click(button());
  }

  it("is enabled only when a position has a label and no compound, and says so when disabled", () => {
    // Position 1 has a label and a compound; 2 and 3 have no label.
    renderTable();
    expect(button()).toBeDisabled();
    expect(button()).toHaveAttribute("title", "Every labeled position already has a compound.");
    // The title of a disabled button shows only while it takes the pointer.
    expect(button()).toHaveClass("disabled:pointer-events-auto");
    cleanup();
    renderTable({ rows: labelled });
    expect(button()).toBeEnabled();
    expect(button()).not.toHaveAttribute("title");
  });

  it("asks about the labels of the positions without a compound, each once", () => {
    renderTable({
      rows: [...labelled, { ...labelled[2], key: "p7", positionLabel: "Position 7" }],
    });
    matchFromLabels(() => undefined);
    expect(match.mutate).toHaveBeenCalledWith(
      { labels: ["SACC-0000002", "DMSO", "SACC-0000004", "160 CoA"] },
      expect.anything(),
    );
  });

  it("fills the matched positions only and leaves a chosen compound as it is", () => {
    const { onReplaceRows, onUpdate } = renderTable({ rows: labelled });
    matchFromLabels((o) => o.onSuccess?.(answer));
    expect(onReplaceRows).toHaveBeenCalledTimes(1);
    expect(onUpdate).not.toHaveBeenCalled();
    const filled = onReplaceRows.mock.calls[0][0] as LabellingRow[];
    expect(filled[1]).toEqual({
      ...labelled[1],
      moleculeId: "m2",
      moleculeName: "Compound two",
      moleculeRef: "REG-0002",
      batchId: "b2",
      batchNumber: "B-2",
    });
    // Several batches: the compound is filled, the batch is left to choose.
    expect(filled[3]).toEqual({
      ...labelled[3],
      moleculeId: "m4",
      moleculeName: "Compound four",
      moleculeRef: "REG-0004",
    });
    for (const i of [0, 2, 4, 5]) expect(filled[i]).toBe(labelled[i]);
  });

  /** A second position that has a compound already. */
  const alsoMatched: LabellingRow = { ...rows[0], key: "p0", positionLabel: "Position 0" };
  const noneFound: PositionLabelMatchesResponse = {
    matches: answer.matches.map((m) => ({ ...m, compound: null })),
  };
  const AMBER = "border-amber-500/30";

  it("says how many positions matched, how many already were, that nothing is saved yet, and which labels found no compound", () => {
    renderTable({ rows: labelled });
    matchFromLabels((o) => o.onSuccess?.(answer));
    const notice = screen.getByText(
      "Matched 2 positions from their labels. 1 was already matched. Nothing is saved until you press Import.",
    );
    const unmatched = within(notice).getByText("No compound found for: DMSO, 160 CoA");
    expect(unmatched).toHaveClass("text-muted-foreground");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Above the table.
    const table = screen.getByRole("table");
    expect(notice.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("says Save where the table is saved, and counts one position in the singular", () => {
    renderTable({ rows: labelled.slice(0, 2), showUse: false });
    matchFromLabels((o) => o.onSuccess?.(answer));
    expect(
      screen.getByText(
        "Matched 1 position from its label. 1 was already matched. Nothing is saved until you press Save.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No compound found for/)).not.toBeInTheDocument();
  });

  it("counts several positions that were already matched in the plural", () => {
    renderTable({ rows: [alsoMatched, ...labelled.slice(0, 2)] });
    matchFromLabels((o) => o.onSuccess?.(answer));
    expect(
      screen.getByText(
        "Matched 1 position from its label. 2 were already matched. Nothing is saved until you press Import.",
      ),
    ).toBeInTheDocument();
  });

  it("does not speak of positions already matched when there were none", () => {
    renderTable({ rows: labelled.slice(1) });
    matchFromLabels((o) => o.onSuccess?.(answer));
    expect(
      screen.getByText(
        "Matched 2 positions from their labels. Nothing is saved until you press Import.",
      ),
    ).toBeInTheDocument();
  });

  // The wizard matches on its own when the file is read: pressing the button afterwards
  // finds nothing new, which is not a failure.
  it("says, without a warning, how many positions are already matched when no label found a new compound", () => {
    const { onReplaceRows } = renderTable({
      rows: [alsoMatched, rows[0], labelled[2], labelled[4]],
    });
    matchFromLabels((o) => o.onSuccess?.(noneFound));
    const notice = screen.getByText(
      "2 positions are already matched. No compound found for: DMSO, 160 CoA.",
    );
    expect(notice).not.toHaveClass(AMBER);
    expect(notice.className).not.toMatch(/amber|green|destructive/);
    expect(screen.queryByText(/No label matched/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onReplaceRows).not.toHaveBeenCalled();
  });

  it("counts one position that is already matched in the singular", () => {
    renderTable({ rows: labelled });
    matchFromLabels((o) => o.onSuccess?.(noneFound));
    expect(
      screen.getByText(
        "1 position is already matched. No compound found for: SACC-0000002, DMSO, SACC-0000004, 160 CoA.",
      ),
    ).not.toHaveClass(AMBER);
  });

  it("warns that no label matched, lists the labels, and leaves the table alone, when no position has a compound", () => {
    const { onReplaceRows } = renderTable({ rows: labelled.slice(1) });
    matchFromLabels((o) => o.onSuccess?.(noneFound));
    expect(
      screen.getByText(
        "No label matched a registered compound. No compound found for: SACC-0000002, DMSO, SACC-0000004, 160 CoA.",
      ),
    ).toHaveClass(AMBER);
    expect(screen.queryByText(/already matched/)).not.toBeInTheDocument();
    expect(onReplaceRows).not.toHaveBeenCalled();
  });

  it("leaves the list out when no label is left to report", () => {
    // As when every label was edited while the answer was on its way.
    renderTable({ rows: labelled.slice(1) });
    matchFromLabels((o) => o.onSuccess?.({ matches: [] }));
    expect(screen.getByText("No label matched a registered compound.")).toHaveClass(AMBER);
    cleanup();
    renderTable({ rows: labelled });
    matchFromLabels((o) => o.onSuccess?.({ matches: [] }));
    expect(screen.getByText("1 position is already matched.")).not.toHaveClass(AMBER);
  });

  it("lists the first 20 labels that found no compound and counts the rest", () => {
    const many = Array.from({ length: 25 }, (_, i) => ({
      ...blank,
      key: `u${i}`,
      positionLabel: `Position ${i + 10}`,
      label: `U${i + 1}`,
    }));
    const unknown = many.map((r) => ({ label: r.label, compound: null }));
    const listed = Array.from({ length: 20 }, (_, i) => `U${i + 1}`).join(", ");
    renderTable({ rows: [...labelled, ...many] });
    matchFromLabels((o) => o.onSuccess?.({ matches: [answer.matches[0], ...unknown] }));
    expect(screen.getByText(`No compound found for: ${listed} and 5 more`)).toBeInTheDocument();
    cleanup();
    renderTable({ rows: [rows[0], ...many] });
    matchFromLabels((o) => o.onSuccess?.({ matches: unknown }));
    expect(
      screen.getByText(
        `1 position is already matched. No compound found for: ${listed} and 5 more.`,
      ),
    ).toBeInTheDocument();
    cleanup();
    renderTable({ rows: many });
    matchFromLabels((o) => o.onSuccess?.({ matches: unknown }));
    expect(
      screen.getByText(
        `No label matched a registered compound. No compound found for: ${listed} and 5 more.`,
      ),
    ).toBeInTheDocument();
  });

  it("is disabled, with the reason as its title, where the compound cannot change", () => {
    renderTable({ rows: labelled, showUse: false, calculatedLocked: "These cannot change now." });
    expect(button()).toBeDisabled();
    expect(button()).toHaveAttribute("title", "These cannot change now.");
    cleanup();
    // With nothing to match either, the lock is still the reason given.
    renderTable({ showUse: false, calculatedLocked: "These cannot change now." });
    expect(button()).toHaveAttribute("title", "These cannot change now.");
  });

  it("reads Matching… and is disabled while the labels are looked up", () => {
    match.isPending = true;
    try {
      renderTable({ rows: labelled });
      expect(screen.getByRole("button", { name: "Matching…" })).toBeDisabled();
    } finally {
      match.isPending = false;
    }
  });

  it("shows the API's reason when the labels cannot be looked up and leaves the table alone", () => {
    const { onReplaceRows } = renderTable({ rows: labelled });
    matchFromLabels((o) => o.onError?.(new Error("API error: 404 — Run not found")));
    expect(screen.getByRole("alert")).toHaveTextContent("Run not found");
    expect(onReplaceRows).not.toHaveBeenCalled();
  });

  it("replaces a file's messages, and a file read afterwards replaces its own", () => {
    const { container } = renderTable({ rows: labelled });
    fillFromFile(container, (o) => o.onError?.(new Error("API error: 422 — File is empty")));
    matchFromLabels((o) => o.onSuccess?.(answer));
    expect(screen.queryByText("File is empty")).not.toBeInTheDocument();
    expect(screen.getByText(/Matched 2 positions from their labels/)).toBeInTheDocument();
    fillFromFile(container, (o) => o.onError?.(new Error("API error: 422 — File is empty")));
    expect(screen.queryByText(/Matched 2 positions/)).not.toBeInTheDocument();
  });

  // The server reads a label as the import does, also by the part before a "(...)";
  // the table sends, finds and lists each label as it is written.
  it("asks about a label with a bracketed suffix as written, fills it, and lists an unmatched one as written", () => {
    const suffixed: LabellingRow[] = [
      { ...blank, key: "s1", positionLabel: "Position 1", label: "SACC-0000002 (50 µM)" },
      { ...blank, key: "s2", positionLabel: "Position 2", label: "SACC-0000002" },
      { ...blank, key: "s3", positionLabel: "Position 3", label: " DMSO (5%) " },
    ];
    const { onReplaceRows } = renderTable({ rows: suffixed });
    matchFromLabels((o) =>
      o.onSuccess?.({
        matches: [
          { label: "SACC-0000002 (50 µM)", compound: oneBatch },
          { label: "SACC-0000002", compound: oneBatch },
          { label: "DMSO (5%)", compound: null },
        ],
      }),
    );
    expect(match.mutate).toHaveBeenCalledWith(
      { labels: ["SACC-0000002 (50 µM)", "SACC-0000002", "DMSO (5%)"] },
      expect.anything(),
    );
    const filled = onReplaceRows.mock.calls[0][0] as LabellingRow[];
    expect(filled.map((r) => r.moleculeId)).toEqual(["m2", "m2", null]);
    expect(filled.map((r) => r.label)).toEqual(suffixed.map((r) => r.label));
    expect(screen.getByText(/Matched 2 positions from their labels/)).toBeInTheDocument();
    expect(screen.getByText("No compound found for: DMSO (5%)")).toBeInTheDocument();
  });
});
