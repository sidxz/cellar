import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/shared/lib/api/custom-instance";
import { valuesOf } from "../lib/position-edits";
import type { LayoutFile, RelabelResult, Run, RunCurves } from "../types";

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

type MutateOptions = {
  onSuccess?: (data: RelabelResult) => void;
  onError?: (e: unknown) => void;
};
const mutate = vi.fn<(body: unknown, opts?: MutateOptions) => void>();
vi.mock("../hooks/use-relabel-positions", () => ({
  useRelabelPositions: () => ({ mutate, isPending: false }),
}));
const toast = vi.hoisted(() => ({ showSuccess: vi.fn(), showWarning: vi.fn() }));
vi.mock("@/shared/lib/toast", () => toast);
// The pickers query the API; their own behaviour is covered where they live.
vi.mock("@/features/inventory/components/molecule-selector", () => ({
  MoleculeSelector: ({
    onSelect,
  }: {
    onSelect: (id: string, mol: { name: string }) => void;
  }) => (
    <button type="button" onClick={() => onSelect("m9", { name: "ABC-0000009" })}>
      compound picker
    </button>
  ),
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

import { EditLabellingDialog } from "./edit-labelling-dialog";

type Position = RunCurves["positions"][number];

const positions: Position[] = [
  {
    well_id: "w1",
    position: "A1",
    row: "A",
    column: 1,
    well_type: "reference",
    batch_id: "b1",
    batch_number: "B-1",
    molecule_id: "m1",
    molecule_name: "ABC-0000001",
    registration_number: "REG-0001",
    dose: 10,
    position_label: "Position 1",
    label: "Protein alone",
    note: null,
  },
  {
    well_id: "w2",
    position: "A2",
    row: "A",
    column: 2,
    well_type: "sample",
    batch_id: "b2",
    batch_number: "B-2",
    molecule_id: "m2",
    molecule_name: "ABC-0000002",
    registration_number: "REG-0002",
    dose: 50,
    position_label: "Position 2",
    label: "x",
    note: null,
  },
];

const draftRun: Pick<Run, "id" | "status" | "is_locked"> = {
  id: "r1",
  status: "draft",
  is_locked: false,
};
const completedRun: Pick<Run, "id" | "status" | "is_locked"> = { ...draftRun, status: "completed" };

function renderDialog(
  props: Partial<Parameters<typeof EditLabellingDialog>[0]> = {},
): ReturnType<typeof render> & { onOpenChange: ReturnType<typeof vi.fn> } {
  const onOpenChange = vi.fn();
  const view = render(
    <EditLabellingDialog
      run={draftRun}
      positions={positions}
      doseUnit="µM"
      open
      onOpenChange={onOpenChange}
      onReload={vi.fn(async () => undefined)}
      {...props}
    />,
  );
  return { ...view, onOpenChange };
}

const COMPUTE_WARNING =
  "The labeling was saved, but the calculations could not be updated. Select Recompute on the run to update them.";
const save = () => screen.getByRole("button", { name: "Save" });
const label = (position: string) => screen.getByRole("textbox", { name: `Label for ${position}` });

beforeEach(() => {
  mutate.mockReset();
  toast.showSuccess.mockReset();
  toast.showWarning.mockReset();
});

describe("EditLabellingDialog", () => {
  it("keeps Save disabled until something changes, then shows the count beside it", () => {
    renderDialog();
    expect(screen.getByRole("heading", { name: "Edit labeling" })).toBeInTheDocument();
    expect(save()).toBeDisabled();
    expect(screen.queryByText(/positions? changed/)).not.toBeInTheDocument();
    fireEvent.change(label("Position 2"), { target: { value: "y" } });
    expect(save()).toBeEnabled();
    const count = screen.getByText("1 position changed");
    expect(save()).not.toContainElement(count);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("sends only the changed rows with the values the dialog opened with", () => {
    const { onOpenChange } = renderDialog();
    fireEvent.change(label("Position 2"), { target: { value: "y" } });
    fireEvent.click(save());
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      positions: [
        {
          well_id: "w2",
          expected: valuesOf(positions[1]),
          new: { ...valuesOf(positions[1]), label: "y" },
        },
      ],
    });
    mutate.mock.calls[0][1]?.onSuccess?.({
      positions_changed: 1,
      readouts_repointed: 0,
      recalculated: false,
      compute_warning: COMPUTE_WARNING,
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toast.showSuccess).toHaveBeenCalledWith("Labeling saved");
    // The API words the warning in full; the dialog shows it as sent.
    expect(toast.showWarning).toHaveBeenCalledWith(COMPUTE_WARNING);
  });

  it("asks for a reason on a completed run and keeps Save disabled without one", () => {
    renderDialog({ run: completedRun });
    fireEvent.change(label("Position 1"), { target: { value: "Protein, buffer" } });
    expect(save()).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Reason" }), {
      target: { value: "Typo" },
    });
    expect(save()).toBeEnabled();
    fireEvent.click(save());
    expect(mutate.mock.calls[0][0]).toMatchObject({ reason: "Typo" });
  });

  it("asks for no reason on a draft run", () => {
    renderDialog();
    expect(screen.queryByRole("textbox", { name: "Reason" })).not.toBeInTheDocument();
  });

  it("shows role, compound, batch and concentration read-only on a completed run", () => {
    renderDialog({ run: completedRun });
    expect(
      screen.getByText(
        "Role, compound, batch and concentration can be changed only while the run is draft or in progress.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /^role for/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^concentration for/i })).not.toBeInTheDocument();
    expect(screen.queryByText("batch picker")).not.toBeInTheDocument();
    expect(label("Position 1")).toBeEnabled();
    expect(screen.getAllByRole("textbox", { name: /^note for/i })[0]).toBeEnabled();
  });

  it("counts rows with a compound and no batch beside Save", () => {
    renderDialog();
    const row = screen.getByText("Position 1").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Change compound for Position 1" }));
    fireEvent.click(within(row).getByRole("button", { name: "compound picker" }));
    expect(
      screen.getByText(
        "1 position has a compound but no batch. Choose a batch to link its traces and values to the compound.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("1 position changed")).toBeInTheDocument();
    fireEvent.click(save());
    expect(mutate.mock.calls[0][0]).toMatchObject({
      positions: [{ well_id: "w1", new: { batch_id: null } }],
    });
  });

  it("on a stale edit shows the API's message and Reload, and Reload refills the table", async () => {
    const onReload = vi.fn(async () => undefined);
    const { rerender } = renderDialog({ onReload });
    fireEvent.change(label("Position 2"), { target: { value: "mine" } });
    fireEvent.click(save());
    mutate.mock.calls[0][1]?.onError?.(
      new ApiError("API error: 409 — Position 2 was changed since you opened it", 409, {
        error: "StaleEditError",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Position 2 was changed since you opened it",
    );
    fireEvent.click(screen.getByRole("button", { name: "Discard edits and reload" }));
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));
    const fresh = positions.map((p) => (p.well_id === "w2" ? { ...p, label: "theirs" } : p));
    rerender(
      <EditLabellingDialog
        run={draftRun}
        positions={fresh}
        doseUnit="µM"
        open
        onOpenChange={vi.fn()}
        onReload={onReload}
      />,
    );
    await waitFor(() => expect(label("Position 2")).toHaveValue("theirs"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  it("keeps the edits and shows the API's message on another refusal", () => {
    renderDialog();
    fireEvent.change(label("Position 2"), { target: { value: "mine" } });
    fireEvent.click(save());
    mutate.mock.calls[0][1]?.onError?.(
      new ApiError("API error: 422 — The batch does not belong to this workspace", 422, {}),
    );
    return waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "The batch does not belong to this workspace",
      );
      expect(
        screen.queryByRole("button", { name: "Discard edits and reload" }),
      ).not.toBeInTheDocument();
      expect(label("Position 2")).toHaveValue("mine");
      expect(save()).toBeEnabled();
    });
  });

  it("offers no Reload on a conflict a reload cannot help, such as a campaign refusal", async () => {
    renderDialog();
    fireEvent.change(label("Position 2"), { target: { value: "mine" } });
    fireEvent.click(save());
    mutate.mock.calls[0][1]?.onError?.(
      new ApiError("API error: 409 — Position 2: campaign 'C' may hold values", 409, {
        error: "ConflictError",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("campaign 'C' may hold values");
    expect(
      screen.queryByRole("button", { name: "Discard edits and reload" }),
    ).not.toBeInTheDocument();
    expect(label("Position 2")).toHaveValue("mine");
  });

  it("gives the label a placeholder that does not speak of a file", () => {
    renderDialog();
    expect(label("Position 1")).toHaveAttribute("placeholder", "No label");
  });

  it("offers a template without a Use column, and a filled table counts as changes to save", () => {
    download.saveText.mockReset();
    const { container } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Download template" }));
    const csv = download.saveText.mock.calls[0][0] as string;
    expect(csv.split("\r\n")[0]).toBe(
      "\uFEFFPosition,Label,Role,Compound,Batch,Concentration (µM),Note",
    );
    expect(save()).toBeDisabled();
    resolve.mutate.mockImplementation((_vars, opts) =>
      opts?.onSuccess?.({
        rows: [
          {
            position: "Position 2",
            label: "from file",
            note: null,
            well_type: null,
            dose: null,
            use: null,
            compound: null,
            problems: [],
          },
        ],
        unrecognised_columns: [],
        calculated_columns_ignored: false,
      }),
    );
    const input = container.ownerDocument.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "layout.csv")] } });
    expect(label("Position 2")).toHaveValue("from file");
    expect(screen.getByText("1 position changed")).toBeInTheDocument();
    expect(
      screen.getByText("Filled 1 position from layout.csv. Nothing is saved until you press Save."),
    ).toBeInTheDocument();
    expect(save()).toBeEnabled();
    expect(mutate).not.toHaveBeenCalled();
  });
});
