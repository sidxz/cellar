import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { type Filter, membershipKey } from "../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { FilterRail, NoRowsMatch } from "./filter-rail";

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => null }));

// RDKit/Ketcher-free shim: the editor applies benzene as SMILES.
vi.mock("@/shared/components/chemistry", () => ({
  StructureRenderer: () => null,
  StructureEditorDialog: ({
    open,
    initialStructure,
    onApply,
  }: {
    open: boolean;
    initialStructure?: string;
    onApply: (s: string, f: string) => void;
  }) =>
    open ? (
      <button
        type="button"
        data-initial={initialStructure}
        onClick={() => onApply("c1ccccc1", "smiles")}
      >
        Apply drawing
      </button>
    ) : null,
}));

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { ApiError, customInstance } from "@/shared/lib/api/custom-instance";

// Radix Popover / cmdk need these in jsdom.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 6,
  row_ids: ["w0", "w1", "w2", "w3", "w4", "w5"],
  columns: [
    { key: "inh", label: "% inhibition", kind: "number", unit: "%", provenance: {} },
    { key: "well_type", label: "Well type", kind: "category", provenance: {} },
    { key: "plate", label: "Plate", kind: "category", provenance: {} },
    { key: "molecule_id", label: "Molecule", kind: "text", provenance: {}, hidden: true },
  ],
  values: {
    inh: [10, 20, 80, 90, 50, 60],
    well_type: ["sample", "sample", "sample", "negative_control", "blank", "sample"],
    plate: ["1", "1", "2", "2", "1", null],
    molecule_id: ["m1", "m1", "m2", null, null, "m3"],
  },
};
const inhAbove = (min: number): Filter => ({
  id: "f-inh",
  kind: "range",
  key: "inh",
  min,
  max: null,
  includeMissing: true,
});
const types = (values: string[]): Filter => ({
  id: "f-type",
  kind: "category",
  key: "well_type",
  values,
  includeMissing: true,
});

function Probe() {
  const filters = useWorkbench((s) => s.filters);
  const history = useWorkbench((s) => s.past.length);
  const undo = useWorkbench((s) => s.undo);
  return (
    <>
      <output data-testid="state">{JSON.stringify({ history, filters })}</output>
      <button type="button" onClick={undo}>
        Undo
      </button>
    </>
  );
}
const state = (): { history: number; filters: Filter[] } =>
  JSON.parse(screen.getByTestId("state").textContent ?? "{}");

const show = (filters: Filter[], children = <FilterRail ds={ds} />) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <WorkbenchProvider initialPanels={[]} initialFilters={filters}>
        {children}
        <Probe />
      </WorkbenchProvider>
    </QueryClientProvider>,
  );

beforeEach(() => vi.mocked(customInstance).mockReset());

const addFilter = (label: string) => {
  fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
  fireEvent.click(screen.getByRole("option", { name: label }));
};

describe("FilterRail", () => {
  it("counts active filters, notes fixed bins, and resets all in one undo step", () => {
    show([inhAbove(50), types(["sample", "negative_control", "blank"])]);
    expect(screen.getByRole("heading", { name: "Filters (1 active)" })).toBeInTheDocument();
    expect(
      screen.getByText("Histograms use fixed bins and show rows that pass the other filters."),
    ).toBeInTheDocument();
    // Only the active card's summary is highlighted.
    expect(screen.getByRole("button", { name: "% inhibition ≥ 50" })).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByRole("button", { name: "Well type: all 3" })).toHaveAttribute(
      "data-active",
      "false",
    );

    fireEvent.click(screen.getByRole("button", { name: "Reset all" }));
    expect(state()).toEqual({ history: 1, filters: [] });
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(state().filters).toHaveLength(2);
  });

  it("adds a range filter for a number and a checklist for a category, keeping every row", () => {
    show([]);
    addFilter("% inhibition");
    addFilter("Plate");
    expect(state().history).toBe(2);
    expect(state().filters).toMatchObject([
      { kind: "range", key: "inh", min: null, max: null, includeMissing: true },
      { kind: "category", key: "plate", values: ["1", "2"], includeMissing: true },
    ]);
    expect(screen.getByRole("heading", { name: "Filters (0 active)" })).toBeInTheDocument();
    // "(none)" is the plate-less row's entry.
    expect(screen.getByRole("button", { name: "Plate: all 3" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /\(none\)/ })).toBeChecked();
  });

  it("counts category values over the other filters but not its own", () => {
    show([inhAbove(50), types(["sample"])]);
    const card = screen.getByRole("group", { name: "Well type" });
    expect(screen.getByRole("button", { name: "Well type: 1 of 3" })).toBeInTheDocument();
    // inh ≥ 50 keeps w2, w3, w4, w5: 2 samples, 1 negative control, 1 blank.
    expect(within(card).getByRole("checkbox", { name: "Sample 2" })).toBeChecked();
    expect(within(card).getByRole("checkbox", { name: "Negative control 1" })).not.toBeChecked();
    fireEvent.click(within(card).getByRole("checkbox", { name: "Blank 1" }));
    expect(state().filters[1]).toMatchObject({ values: ["sample", "blank"] });
    expect(state().history).toBe(1);
  });

  it("lists the Other, No value and Not tested buckets after the named values", () => {
    const series: Dataset = {
      ...ds,
      columns: [...ds.columns, { key: "s", label: "Series", kind: "category", provenance: {} }],
      values: { ...ds.values, s: ["Other", "Not tested", "Amides", "No value", "Zeta", null] },
    };
    const filter: Filter = { ...types([]), key: "s", values: [] };
    show([filter], <FilterRail ds={series} />);
    const card = screen.getByRole("group", { name: "Series" });
    expect(
      within(card)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Amides1", "Zeta1", "No value1", "Not tested1", "Other1", "(none)1"]);
  });

  it("names a filter on a removed column by its last label, inert and removable", () => {
    const r1: Filter = {
      id: "f-r1",
      kind: "category",
      key: "chem:rg1:R1",
      values: ["Cl"],
      includeMissing: false,
    };
    const x: Filter = {
      id: "f-x",
      kind: "range",
      key: "chem:clusters:x",
      min: 1,
      max: null,
      includeMissing: true,
    };
    show([r1, x], <FilterRail ds={ds} labels={new Map([["chem:rg1:R1", "R1"]])} />);
    expect(screen.getByRole("heading", { name: "Filters (0 active)" })).toBeInTheDocument();
    const card = screen.getByRole("group", { name: "R1 (removed column)" });
    expect(card.textContent).not.toMatch(/chem:/);
    expect(within(card).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "R1 (removed column): not applied" }),
    ).toHaveAttribute("data-active", "false");
    // Never seen here: no label to show, still no raw key.
    expect(screen.getByRole("group", { name: "Removed column" }).textContent).not.toMatch(/chem:/);
    fireEvent.click(screen.getByRole("button", { name: "Remove filter R1 (removed column)" }));
    expect(state().filters.map((f) => f.id)).toEqual(["f-x"]);
  });

  it("shows Filter to selection as a removable card", () => {
    show([{ id: "selection", kind: "rows", rowIds: ["w0", "w1"] }]);
    expect(screen.getByRole("button", { name: "Selection: 2 rows" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Selection" }));
    expect(state().filters).toEqual([]);
  });
});

describe("FilterRail substructure", () => {
  const drawBenzene = () => {
    addFilter("Substructure…");
    fireEvent.click(screen.getByRole("button", { name: "Apply drawing" }));
  };

  it("matches the dataset's compounds and adds the filter in one undo step", async () => {
    let answer: (body: unknown) => void = () => {};
    vi.mocked(customInstance).mockReturnValueOnce(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    show([]);
    drawBenzene();
    expect(await screen.findByText("Matching…")).toBeInTheDocument();
    answer({ matched_ids: ["m2"], searched: 3, without_structure: 0 });
    expect(await screen.findByText("1 of 3 compounds match")).toBeInTheDocument();
    expect(vi.mocked(customInstance)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/visualization/substructure-match",
        method: "POST",
        data: { query: "c1ccccc1", query_kind: "smiles", molecule_ids: ["m1", "m2", "m3"] },
      }),
    );
    expect(state()).toEqual({
      history: 1,
      filters: [
        {
          id: expect.stringMatching(/^sub-/),
          kind: "substructure",
          query: "c1ccccc1",
          queryKind: "smiles",
          moleculeIds: ["m2"],
          over: membershipKey(ds),
        },
      ],
    });
    expect(screen.queryByText("Matching…")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Filters (1 active)" })).toBeInTheDocument();
  });

  it("adds both of two queries drawn while the first still matches, each its own filter", async () => {
    const answers: ((body: unknown) => void)[] = [];
    for (const _ of [1, 2]) {
      vi.mocked(customInstance).mockReturnValueOnce(
        new Promise((resolve) => {
          answers.push(resolve);
        }),
      );
    }
    show([]);
    drawBenzene();
    addFilter("Substructure…");
    fireEvent.click(screen.getByRole("button", { name: "Apply drawing" }));
    await waitFor(() => expect(answers).toHaveLength(2));
    answers[0]({ matched_ids: ["m1"], searched: 3, without_structure: 0 });
    answers[1]({ matched_ids: ["m2"], searched: 3, without_structure: 0 });
    await waitFor(() => expect(state().filters).toHaveLength(2));
    const [a, b] = state().filters;
    expect(a.id).not.toBe(b.id);
    expect(state().filters.map((f) => f.kind === "substructure" && f.moleculeIds)).toEqual([
      ["m1"],
      ["m2"],
    ]);
  });

  it("shows the server's message for an unreadable query and adds no filter", async () => {
    const message =
      "Cannot read \u201cC1CC\u201d as a SMILES structure. Check ring closures, brackets and charges.";
    vi.mocked(customInstance).mockRejectedValueOnce(
      new ApiError(`API error: 422 \u2014 ${message}`, 422, { error: "ValidationError", message }),
    );
    show([]);
    drawBenzene();
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(state()).toEqual({ history: 0, filters: [] });
    // Edit query reopens the editor on the query that failed.
    fireEvent.click(screen.getByRole("button", { name: "Edit query" }));
    expect(screen.getByRole("button", { name: "Apply drawing" })).toHaveAttribute(
      "data-initial",
      "c1ccccc1",
    );
  });

  it("is unavailable when the dataset has no compounds", () => {
    const noCompounds: Dataset = {
      ...ds,
      values: { ...ds.values, molecule_id: ds.row_ids.map(() => null) },
    };
    show([], <FilterRail ds={noCompounds} />);
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    expect(screen.getByRole("option", { name: /Substructure…/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});

describe("NoRowsMatch", () => {
  const guarded = (
    <NoRowsMatch ds={ds}>
      <p>plots</p>
    </NoRowsMatch>
  );

  it("lists the active filters with a Clear button when nothing passes", () => {
    show([inhAbove(70), types(["blank"])], guarded);
    expect(screen.queryByText("plots")).not.toBeInTheDocument();
    expect(screen.getByText("No rows match")).toBeInTheDocument();
    expect(screen.getByText("% inhibition ≥ 70")).toBeInTheDocument();
    expect(screen.getByText("Well type: 1 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(state().filters).toEqual([]);
    expect(screen.getByText("plots")).toBeInTheDocument();
  });

  it("lists a substructure that matches nothing", () => {
    show(
      [
        {
          id: "sub-1",
          kind: "substructure",
          query: "C1CCCCC1",
          queryKind: "smiles",
          moleculeIds: [],
          over: membershipKey(ds),
        },
      ],
      guarded,
    );
    expect(screen.getByText("No rows match")).toBeInTheDocument();
    expect(screen.getByText("Contains C1CCCCC1")).toBeInTheDocument();
  });

  it("renders its children while any row passes", () => {
    show([inhAbove(70)], guarded);
    expect(screen.getByText("plots")).toBeInTheDocument();
  });
});
