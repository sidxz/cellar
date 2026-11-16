import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { usePassMask } from "../../hooks/use-pass-mask";
import type { Filter } from "../../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FilterRail } from "../filter-rail";

const plot = vi.hoisted(() => ({ last: null as null | { data: { y: number[] }[] } }));
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: { data: { y: number[] }[] }) => {
    plot.last = p;
    return null;
  },
}));

// jsdom has no PointerEvent; a MouseEvent carrying a pointerId is what Radix reads.
class FakePointerEvent extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 0;
  }
}

beforeAll(() => {
  window.PointerEvent ??= FakePointerEvent as unknown as typeof PointerEvent;
  Element.prototype.setPointerCapture ??= vi.fn();
  Element.prototype.releasePointerCapture ??= vi.fn();
  Element.prototype.hasPointerCapture = vi.fn(() => true);
});

// % inhibition 0…100 (one missing); w4 is a blank.
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 5,
  row_ids: ["w0", "w1", "w2", "w3", "w4"],
  columns: [
    { key: "inh", label: "% inhibition", kind: "number", unit: "%", provenance: {} },
    { key: "well_type", label: "Well type", kind: "category", provenance: {} },
  ],
  values: {
    inh: [0, 30, 50, null, 100],
    well_type: ["sample", "sample", "sample", "sample", "blank"],
  },
};
const range = (patch: Partial<Extract<Filter, { kind: "range" }>> = {}): Filter => ({
  id: "f-inh",
  kind: "range",
  key: "inh",
  min: null,
  max: null,
  includeMissing: true,
  ...patch,
});

function Probe() {
  const filters = useWorkbench((s) => s.filters);
  const history = useWorkbench((s) => s.past.length);
  const mask = usePassMask(ds);
  return (
    <output data-testid="state">
      {JSON.stringify({ history, filters, passing: mask.reduce((n, v) => n + v, 0) })}
    </output>
  );
}
const state = (): { history: number; filters: Filter[]; passing: number } =>
  JSON.parse(screen.getByTestId("state").textContent ?? "{}");
const inh = () => state().filters[0] as Extract<Filter, { kind: "range" }>;

const show = (filters: Filter[]) =>
  render(
    <WorkbenchProvider initialPanels={[]} initialFilters={filters}>
      <FilterRail ds={ds} />
      <Probe />
    </WorkbenchProvider>,
  );

describe("RangeFilterCard", () => {
  it("commits a slider drag once, on release", () => {
    show([range()]);
    const slider = document.querySelector<HTMLElement>("[data-slot=slider]");
    if (!slider) throw new Error("no slider");
    slider.getBoundingClientRect = () =>
      ({ left: 0, right: 100, width: 100, top: 0, bottom: 10, height: 10 }) as DOMRect;
    fireEvent.pointerDown(slider, { clientX: 10, pointerId: 1 });
    fireEvent.pointerMove(slider, { clientX: 20, pointerId: 1 });
    fireEvent.pointerMove(slider, { clientX: 30, pointerId: 1 });
    expect(state().history).toBe(0);
    fireEvent.pointerUp(slider, { clientX: 30, pointerId: 1 });
    expect(state().history).toBe(1);
    expect(inh()).toMatchObject({ min: 30, max: null });
    expect(screen.getByRole("button", { name: "% inhibition ≥ 30" })).toBeInTheDocument();
  });

  it("sets the same filter from the min input on blur, with the unit and inclusive bound", () => {
    show([range()]);
    expect(screen.getByRole("button", { name: "% inhibition 0 … 100" })).toBeInTheDocument();
    const min = screen.getByRole("spinbutton", { name: "Minimum (inclusive)" });
    expect(screen.getAllByText("%")).toHaveLength(2);
    expect(screen.getByText("≥")).toBeInTheDocument();
    fireEvent.change(min, { target: { value: "30" } });
    expect(state().history).toBe(0);
    fireEvent.blur(min);
    expect(state().history).toBe(1);
    expect(inh()).toMatchObject({ id: "f-inh", min: 30, max: null });
    expect(state().passing).toBe(4); // 30, 50, 100 + the missing row
    expect(screen.getByRole("button", { name: "% inhibition ≥ 30" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("collapses to its summary and drops missing rows when the toggle is off", () => {
    show([range({ min: 30 })]);
    const header = screen.getByRole("button", { name: "% inhibition ≥ 30" });
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    fireEvent.click(header);

    const missing = screen.getByRole("checkbox", { name: "Include missing (1)" });
    fireEvent.click(missing);
    expect(inh().includeMissing).toBe(false);
    expect(state().passing).toBe(3);
    fireEvent.click(missing);
    expect(state().passing).toBe(4);
    expect(state().history).toBe(2);
  });

  it("histograms the rows passing the other filters only", () => {
    const noBlanks: Filter = {
      id: "f-type",
      kind: "category",
      key: "well_type",
      values: ["sample"],
      includeMissing: true,
    };
    show([range({ min: 60 }), noBlanks]);
    // Its own bound would leave 1 row; the other filter leaves the 3 measured samples.
    const counts = plot.last?.data[0].y ?? [];
    expect(counts.reduce((a, b) => a + b, 0)).toBe(3);
  });
});
