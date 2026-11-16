import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { Filter } from "../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { FilterRail, NoRowsMatch } from "./filter-rail";

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => null }));

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
  ],
  values: {
    inh: [10, 20, 80, 90, 50, 60],
    well_type: ["sample", "sample", "sample", "negative_control", "blank", "sample"],
    plate: ["1", "1", "2", "2", "1", null],
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
    <WorkbenchProvider initialPanels={[]} initialFilters={filters}>
      {children}
      <Probe />
    </WorkbenchProvider>,
  );

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

  it("shows Filter to selection as a removable card", () => {
    show([{ id: "selection", kind: "rows", rowIds: ["w0", "w1"] }]);
    expect(screen.getByRole("button", { name: "Selection: 2 rows" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Selection" }));
    expect(state().filters).toEqual([]);
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

  it("renders its children while any row passes", () => {
    show([inhAbove(70)], guarded);
    expect(screen.getByText("plots")).toBeInTheDocument();
  });
});
