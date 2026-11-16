import type { DoseResponseCurve } from "@/features/screening-assay/types";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { compoundCurve, provenanceOf } from "../lib/traces/test-fixtures";
import type { Dataset, DatasetColumn, DatasetSource } from "../types";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const R1 = "11111111-1111-4111-8111-111111111111";
const R2 = "22222222-2222-4222-8222-222222222222";
const R3 = "33333333-3333-4333-8333-333333333333";
const U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const P1 = "99999999-9999-4999-8999-999999999999";
const names: Record<string, string> = { [U1]: "A. Chen" };
const runs = [
  { id: R1, run_date: "2026-11-12", status: "approved", conditions: { NADP: "+" } },
  { id: R2, run_date: "2026-11-05", status: "completed", conditions: null },
  { id: R3, run_date: "2026-10-29", status: "draft", conditions: null },
].map((r) => ({ ...r, created_at: "1", operator: U1, plate_count: 1, protocol_id: P1 }));

const state = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  counts: undefined as Record<string, number> | undefined,
  replace: vi.fn(),
  curves: [] as DoseResponseCurve[],
  derived: [] as DerivedEntry[],
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string) => names[id] ?? "",
}));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: runs, isLoading: false }),
  useRun: (id: string) => ({ data: runs.find((r) => r.id === id) }),
}));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocol: () => ({ data: { id: P1, name: "NadD HTS" } }),
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/features/screening-assay/hooks/use-compound-curves", () => ({
  useCompoundCurves: () => ({ data: state.curves, isLoading: false }),
}));
vi.mock("@structflo/components/dose-response", () => ({
  DoseResponseChartView: ({ curves }: { curves: { label?: string }[] }) => (
    <ul aria-label="Chart">
      {curves.map((c) => (
        <li key={c.label}>{c.label}</li>
      ))}
    </ul>
  ),
  DoseResponseFigure: () => null,
}));
vi.mock("../hooks/use-dataset", () => ({ useDataset: () => state.query }));
vi.mock("../hooks/use-derived", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../hooks/use-derived")>();
  return { ...mod, useDerived: () => mod.useDerived(state.derived) };
});
vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));
// Jobs never start here; the bar shows what was asked for.
vi.mock("./derived-runner", () => ({ DerivedRunner: () => null }));
vi.mock("./derived/rgroups-dialog", () => ({
  RGroupsDialog: ({
    moleculeIds,
    onApply,
    onOpenChange,
  }: {
    moleculeIds: string[];
    onApply: (core: string) => void;
    onOpenChange: (open: boolean) => void;
  }) => (
    <button
      type="button"
      onClick={() => {
        onApply("c1ccncc1[*:1]");
        onOpenChange(false);
      }}
    >
      Use pyridine core for {moleculeIds.join(", ")}
    </button>
  ),
}));
vi.mock("../hooks/use-run-row-counts", () => ({
  useRunRowCounts: (id: string | null) => ({
    data: id && state.counts ? { counts: state.counts } : undefined,
  }),
}));

import type { DerivedEntry } from "../hooks/use-derived";
import { rgroupSet } from "../lib/derived";
import type { Level } from "../types";
import { WorkbenchPage } from "./workbench-page";

const col = (key: string, kind: DatasetColumn["kind"], hidden = false): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: provenanceOf(key),
  hidden,
});

function dataset(numeric = true): Dataset {
  return {
    revision: "rev",
    level: "wells",
    row_count: 3,
    row_ids: ["w1", "w2", "w3"],
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("plate", "category"),
      col("well_type", "category"),
      col("well_order", "number"),
      col("operator", "user"),
      col("rd:s:raw", numeric ? "number" : "category"),
    ],
    values: {
      compound: ["CEL-1", "CEL-2", null],
      molecule_id: ["m1", "m2", null],
      plate: ["1", "1", "1"],
      well_type: ["sample", "sample", "negative_control"],
      well_order: [1, 2, 3],
      operator: [U1, U1, U1],
      "rd:s:raw": numeric ? [1, 2, 3] : ["a", "b", "c"],
    },
  };
}

/** The same two compounds one row each, as an aggregated level sends them (no wells). */
function aggregated(level: Level, rows = 2): Dataset {
  return {
    revision: `rev-${level}`,
    level,
    row_count: rows,
    row_ids: ["m1", "m2"].slice(0, rows),
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("rd:s:raw", "number"),
    ],
    values: {
      compound: ["CEL-1", "CEL-2"].slice(0, rows),
      molecule_id: ["m1", "m2"].slice(0, rows),
      "rd:s:raw": [1, 2].slice(0, rows),
    },
  };
}

const ready = (ds: Dataset) => ({ data: ds, isPending: false, isError: false, refetch: vi.fn() });

// Radix Popover / cmdk need these in jsdom.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

beforeEach(() => {
  state.derived = [];
  state.replace.mockReset();
  state.counts = undefined;
  state.query = ready(dataset());
});

describe("WorkbenchPage", () => {
  it("shows the server's 422 message with a Retry that refetches", () => {
    const refetch = vi.fn();
    const message = "This selection has 410 columns; the limit is 400. Choose fewer runs.";
    state.query = {
      isPending: false,
      isError: true,
      error: new ApiError(`API error: 422 — ${message}`, 422, { message }),
      refetch,
    };
    render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText(message)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("over the row cap, shows the count and reopens the run picker", () => {
    state.counts = { [R1]: 150_000, [R2]: 100_000, [R3]: 0 };
    render(<WorkbenchPage level="wells" source={{ kind: "protocol", protocolId: P1 }} />);
    expect(screen.getByText(/250,000 wells/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose fewer runs" }));
    expect(screen.getByRole("dialog", { name: "Choose runs to visualize" })).toBeInTheDocument();
  });

  it("leaves Add columns reachable without structures, saying why it is unavailable", () => {
    render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    const add = screen.getByRole("button", { name: "Add columns" });
    expect(add).toHaveAttribute("aria-disabled", "true");
    expect(add).toBeEnabled();
    expect(add).toHaveAccessibleDescription("No compound in this dataset has a structure");
    fireEvent.keyDown(add, { key: "Enter" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("says so when the runs have no readout data", () => {
    state.query = ready({ ...dataset(), row_count: 0, row_ids: [], values: {} });
    render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText("These runs have no readout data yet")).toBeInTheDocument();
  });

  it("flags a dataset with no numeric fields", () => {
    state.query = ready(dataset(false));
    render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText(/no numeric fields to plot/i)).toBeInTheDocument();
  });

  it("heads the workbench with the source, grain, counts and history buttons", () => {
    render(
      <WorkbenchPage
        level="wells"
        source={{ kind: "protocol", protocolId: P1, runIds: [R1, R2] }}
      />,
    );
    expect(screen.getByRole("link", { name: /NadD HTS/ })).toHaveAttribute(
      "href",
      `/assays/protocols/${P1}`,
    );
    expect(screen.getByText("Each row: one well")).toBeInTheDocument();
    expect(screen.getByText("3 / 3 wells · 2 compounds")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Redo" })).toBeDisabled();
  });

  it("lists the source runs as date · operator in the popover, with no UUIDs", () => {
    render(
      <WorkbenchPage
        level="wells"
        source={{ kind: "protocol", protocolId: P1, runIds: [R1, R2] }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /2 of 3 runs/ }));
    expect(screen.getByText("2026-11-12 · A. Chen")).toBeInTheDocument();
    expect(screen.getByText("2026-11-05 · A. Chen")).toBeInTheDocument();
    expect(screen.queryByText(/2026-10-29/)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it("updates the header count as a rail filter narrows the rows", () => {
    render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "rd:s:raw" }));
    expect(screen.getByText("3 / 3 wells · 2 compounds")).toBeInTheDocument();
    const min = screen.getByRole("spinbutton", { name: "Minimum (inclusive)" });
    fireEvent.change(min, { target: { value: "2" } });
    fireEvent.keyDown(min, { key: "Enter" });
    expect(screen.getByText("2 / 3 wells · 1 compound")).toBeInTheDocument();
  });

  it("keeps the workbench on screen when a background refetch fails", () => {
    const { rerender } = render(
      <WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />,
    );
    state.query = { ...ready(dataset()), isError: true, error: new Error("Network error") };
    rerender(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    expect(screen.queryByText("Couldn't load the data")).not.toBeInTheDocument();
    expect(screen.getByText("3 / 3 wells · 2 compounds")).toBeInTheDocument();
  });

  it("keeps the chemist's plots, filters and history when new data arrives", () => {
    const { rerender } = render(
      <WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />,
    );
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "rd:s:raw" }));
    expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
    state.query = ready({ ...dataset(), revision: "rev-2" });
    rerender(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
  });

  it("switches level through the URL, keeping the plots and filters the new level can show", () => {
    const run = { kind: "run", runId: R1 } as const;
    const { rerender } = render(<WorkbenchPage level="wells" source={run} />);
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "well_order" }));
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "rd:s:raw" }));
    fireEvent.click(screen.getByRole("button", { name: "Compounds" }));
    expect(state.replace).toHaveBeenCalledWith(`/assays/visualize?run=${R1}&level=compounds`, {
      scroll: false,
    });

    state.query = ready(aggregated("compounds"));
    rerender(<WorkbenchPage level="compounds" source={run} />);
    expect(screen.getByRole("button", { name: "Compounds" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("Each row: compound")).toBeInTheDocument();
    expect(screen.getByText("2 / 2 compounds")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "well_order" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "rd:s:raw" })).toBeInTheDocument();
    const note = screen.getByRole("status");
    expect(note).toHaveTextContent(
      "Switched to Compounds. Not available at this level: Filter: well_order, " +
        "Plot 1: X (well_order), Plot 1: Color (well_type), Plot 1: Shape (well_type), " +
        "Plot 1: Split (plate), Plot 1: Scatter (now a histogram).",
    );
    // The switch itself is not an undo step.
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss note" }));
    expect(screen.getByRole("status")).toHaveTextContent(/^$/);
    expect(screen.queryByText(/Switched to Compounds/)).not.toBeInTheDocument();
  });

  it("says the selection was cleared only when rows were selected", async () => {
    const run = { kind: "run", runId: R1 } as const;
    const { rerender } = render(<WorkbenchPage level="wells" source={run} />);
    fireEvent.click(screen.getByRole("button", { name: "Batches" }));
    state.query = ready(aggregated("batches"));
    rerender(<WorkbenchPage level="batches" source={run} />);
    expect(screen.getByRole("status")).not.toHaveTextContent(/Selection cleared/);

    fireEvent.click((await screen.findAllByRole("checkbox", { name: "Select row" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "Runs" }));
    state.query = ready(aggregated("runs"));
    rerender(<WorkbenchPage level="runs" source={run} />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Selection cleared — rows differ between levels.",
    );
  });

  it.each([
    ["runs", "Each row: compound × batch × run", "2 / 2 rows · 2 compounds"],
    ["batches", "Each row: compound × batch", "2 / 2 batches · 2 compounds"],
  ] as const)("at %s, captions the grain and counts in its noun", (level, caption, counts) => {
    state.query = ready(aggregated(level));
    render(<WorkbenchPage level={level} source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText(caption)).toBeInTheDocument();
    expect(screen.getByText(counts)).toBeInTheDocument();
  });

  it("leaves the row cap to the server above Wells", () => {
    state.counts = { [R1]: 150_000, [R2]: 100_000, [R3]: 0 };
    state.query = ready(aggregated("compounds"));
    render(<WorkbenchPage level="compounds" source={{ kind: "protocol", protocolId: P1 }} />);
    expect(screen.queryByText(/Too many wells/)).not.toBeInTheDocument();
    expect(screen.getByText("2 / 2 compounds")).toBeInTheDocument();
  });

  it("at Batches over draft runs only, says why it is empty and offers Runs", () => {
    state.query = ready({ ...aggregated("batches", 0), values: {} });
    const source: DatasetSource = { kind: "protocol", protocolId: P1, runIds: [R3] };
    render(<WorkbenchPage level="batches" source={source} />);
    expect(screen.getByText("No completed or approved runs here")).toBeInTheDocument();
    expect(
      screen.getByText("Batches and Compounds count only completed or approved runs."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show Runs" }));
    expect(state.replace).toHaveBeenCalledWith(
      `/assays/visualize?protocol=${P1}&runs=${R3}&level=runs`,
      { scroll: false },
    );
  });

  it("at Compounds, Curves (n) opens the compound's curves over the runs that count", async () => {
    const RD = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
    const geo = { protocol_id: P1, readout_definition_id: RD, layer: null, aggregation: "geomean" };
    const base = aggregated("compounds", 1);
    state.query = ready({
      ...base,
      columns: [
        ...base.columns,
        { key: "dr:e", label: "Enzyme · IC50", kind: "number", provenance: geo },
        {
          key: "dr:e:n_tested",
          label: "n tested",
          kind: "number",
          provenance: { ...geo, stat: "n_tested" },
        },
      ],
      values: { ...base.values, "dr:e": [0.5], "dr:e:n_tested": [2] },
    });
    state.curves = [R1, R2, R3].map((run_id, k) =>
      compoundCurve({
        id: `c${k}`,
        run_id,
        molecule_id: "m1",
        protocol_id: P1,
        readout_definition_id: RD,
        fitted_value: 0.5,
      }),
    );
    render(<WorkbenchPage level="compounds" source={{ kind: "protocol", protocolId: P1 }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Curves (2)" }));
    const chart = within(screen.getByRole("dialog", { name: "CEL-1 · Enzyme · IC50" })).getByRole(
      "list",
      { name: "Chart" },
    );
    // The draft run (2026-10-29) does not count at Compounds.
    expect(
      within(chart)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["2026-11-05 · A. Chen", "2026-11-12 · A. Chen"]);
    expect(document.body.textContent).not.toMatch(UUID);
  });

  describe("with R-group columns", () => {
    const spec = {
      id: "rg1",
      kind: "rgroups",
      coreSmiles: "c1ccccc1[*:1]",
      name: "Core A",
    } as const;
    const withStructures = (ds: Dataset): Dataset => ({
      ...ds,
      columns: [...ds.columns, col("structure", "structure")],
      values: { ...ds.values, structure: ds.values.molecule_id.map((m) => m && "c1ccccc1Cl") },
    });

    beforeEach(() => {
      const base = withStructures(dataset());
      const set = rgroupSet(spec, base, {
        core_smiles: spec.coreSmiles,
        labels: ["R1"],
        assignments: { m1: { R1: "Cl[*:1]" } },
      });
      state.query = ready(base);
      state.derived = [
        { spec, moleculeIds: ["m1", "m2"], status: "ready", set, startedAt: 0, attempt: 1 },
      ];
    });

    const addFilter = (name: string) => {
      fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
      fireEvent.click(screen.getByRole("option", { name }));
    };

    it("keeps a filter on an R-group column across a level switch", () => {
      const run = { kind: "run", runId: R1 } as const;
      const { rerender } = render(<WorkbenchPage level="wells" source={run} />);
      expect(screen.getByText("R-groups · Core A")).toBeInTheDocument();
      addFilter("R1");
      expect(screen.getByRole("group", { name: "R1" })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Compounds" }));
      state.query = ready(withStructures(aggregated("compounds")));
      rerender(<WorkbenchPage level="compounds" source={run} />);
      expect(screen.getByText("Each row: compound")).toBeInTheDocument();
      expect(screen.getByRole("group", { name: "R1" })).toBeInTheDocument();
      expect(screen.getByText("R-groups · Core A")).toBeInTheDocument();
    });

    it("removing the set drops its filter as one undo step and says so", () => {
      render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
      addFilter("R1");
      fireEvent.click(screen.getByRole("button", { name: "Remove R-groups · Core A" }));
      expect(screen.queryByText("R-groups · Core A")).not.toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "R1" })).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(
        "R-groups · Core A removed. Not available now: Filter: R1.",
      );
      // The chemist's history stays: the drop is an ordinary undo step.
      fireEvent.click(screen.getByRole("button", { name: "Undo" }));
      expect(screen.getByText("3 / 3 wells · 2 compounds")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
      // The filter undo brought back reads by its column's last label, never its key.
      expect(screen.getByRole("group", { name: "R1 (removed column)" })).toBeInTheDocument();
    });

    it("numbers a new R-groups set past a removed one, over the compounds with a structure", () => {
      render(<WorkbenchPage level="wells" source={{ kind: "run", runId: R1 }} />);
      fireEvent.click(screen.getByRole("button", { name: "Remove R-groups · Core A" }));
      fireEvent.keyDown(screen.getByRole("button", { name: "Add columns" }), { key: "Enter" });
      fireEvent.click(screen.getByRole("menuitem", { name: "R-groups…" }));
      fireEvent.click(screen.getByRole("button", { name: "Use pyridine core for m1, m2" }));
      expect(screen.getByText("R-groups · Core B")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Cancel R-groups · Core B" })).toBeInTheDocument();
      expect(screen.queryByText("R-groups · Core A")).not.toBeInTheDocument();
    });
  });
});
