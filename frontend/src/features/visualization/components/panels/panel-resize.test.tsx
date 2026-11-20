import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { panelDefaults } from "../../lib/default-panels";
import { matrixWells } from "../../lib/traces/test-fixtures";
import { WorkbenchProvider, useWorkbench } from "../../store/workbench-context";
import { makePanel } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { PanelGrid } from "../panel-grid";

vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));

// The real shared Plot over a stand-in react-plotly: each graph div reports itself drawn
// once, at the full width a lone panel has.
const drawn = vi.hoisted(() => new WeakSet<Element>());
vi.mock("next/dynamic", () => ({
  default: () => (props: { onInitialized?: (f: unknown, gd: HTMLElement) => void }) => (
    <div
      data-testid="graph"
      ref={(el) => {
        if (!el || drawn.has(el)) return;
        drawn.add(el);
        el.getBoundingClientRect = () => ({ width: 1100, height: 400 }) as DOMRect;
        props.onInitialized?.({}, el);
      }}
    />
  ),
}));

class FakeObserver {
  static all: FakeObserver[] = [];
  watched: Element[] = [];
  constructor(readonly fire: ResizeObserverCallback) {
    FakeObserver.all.push(this);
  }
  observe(el: Element) {
    this.watched.push(el);
  }
  unobserve() {}
  disconnect() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeObserver.all = [];
  (window as { Plotly?: unknown }).Plotly = undefined;
});

/** Wells with R-groups, on two plates. */
function wells(): Dataset {
  const ds = matrixWells();
  return {
    ...ds,
    columns: [
      ...ds.columns,
      { key: "plate", label: "Plate", kind: "category", provenance: {} },
      { key: "well_order", label: "Well order", kind: "number", provenance: {} },
    ],
    values: {
      ...ds.values,
      plate: ["Plate 1", "Plate 1", "Plate 1", "Plate 1", "Plate 2", "Plate 2", "Plate 2"],
      well_order: [1, 2, 3, 4, 1, 2, 3],
    },
  };
}

function AddMatrix({ ds }: { ds: Dataset }) {
  const addPanel = useWorkbench((s) => s.addPanel);
  return (
    <button
      type="button"
      onClick={() => addPanel("rgroup-matrix", panelDefaults(ds, "rgroup-matrix"))}
    >
      add matrix
    </button>
  );
}

describe("a split Wells scatter beside a newly added R-group matrix", () => {
  it("stays mounted and refits to its own half of the grid on the first add", () => {
    vi.stubGlobal("ResizeObserver", FakeObserver);
    const resize = vi.fn(() => Promise.resolve());
    (window as { Plotly?: unknown }).Plotly = { Plots: { resize } };
    const ds = wells();
    const scatter = makePanel("scatter", {
      x: "well_order",
      y: "rd:s:raw",
      appearance: { splitBy: "plate" },
    });
    render(
      <WorkbenchProvider initialPanels={[scatter]}>
        <AddMatrix ds={ds} />
        <PanelGrid ds={ds} onEdit={() => {}} />
      </WorkbenchProvider>,
    );
    const [graph] = screen.getAllByTestId("graph");
    const [observer] = FakeObserver.all;
    expect(observer.watched).toEqual([graph]);
    // The observer's first report is the size the graph was just drawn at: no refit.
    const report = (width: number) =>
      observer.fire(
        [{ contentRect: { width, height: 400 } } as ResizeObserverEntry],
        observer as unknown as ResizeObserver,
      );
    report(1100);
    expect(resize).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "add matrix" }));
    expect(screen.getAllByRole("region")).toHaveLength(2);
    // Same graph, same observer: nothing remounted, so nothing waits for a window resize.
    expect(screen.getAllByTestId("graph")).toEqual([graph]);
    expect(FakeObserver.all).toHaveLength(1);

    // The grid's second column halves the scatter's box: it refits to it.
    act(() => report(545));
    expect(resize).toHaveBeenCalledTimes(1);
    expect(resize).toHaveBeenCalledWith(graph);
  });
});
