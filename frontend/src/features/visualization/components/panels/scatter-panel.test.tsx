import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { crossProtocol } from "../../lib/cross-protocol-fixture";
import { WorkbenchProvider, useWorkbench } from "../../store/workbench-context";
import { DEFAULT_APPEARANCE, type PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { ScatterPanel } from "./scatter-panel";

type Handlers = {
  onSelected: (ev: unknown) => void;
  onDeselect: () => void;
  onClick: (ev: unknown) => void;
};
const plot = vi.hoisted(() => ({ last: null as unknown }));
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: unknown) => {
    plot.last = p;
    return null;
  },
}));
const handlers = () => plot.last as Handlers;

const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 3,
  row_ids: ["w0", "w1", "w2"],
  columns: [
    { key: "well_order", label: "Well order", kind: "number", provenance: {} },
    { key: "y", label: "Signal", kind: "number", provenance: {} },
  ],
  values: { well_order: [1, 2, 3], y: [5, null, 7] },
};
const panel: PanelConfig = {
  id: "p1",
  type: "scatter",
  x: "well_order",
  y: "y",
  appearance: DEFAULT_APPEARANCE,
};

function Selection() {
  const selection = useWorkbench((s) => s.selection);
  return <p data-testid="sel">{[...selection].join(",")}</p>;
}

/** A selection made outside the plot (table checkbox, strip, another panel). */
function External() {
  const setSelection = useWorkbench((s) => s.setSelection);
  return (
    <button type="button" onClick={() => setSelection(["w0"])}>
      external
    </button>
  );
}

const show = () =>
  render(
    <WorkbenchProvider initialPanels={[panel]}>
      <ScatterPanel panel={panel} ds={ds} />
      <Selection />
      <External />
    </WorkbenchProvider>,
  );
const drawn = () =>
  plot.last as {
    data: { x: unknown; text: unknown; selectedpoints?: number[] }[];
    layout: { uirevision: string; selectionrevision: string };
  };
const lasso = (...rows: number[]) =>
  act(() =>
    handlers().onSelected({
      lassoPoints: { x: [], y: [] },
      points: rows.map((customdata) => ({ customdata })),
    }),
  );

describe("ScatterPanel", () => {
  it("selects rows by id from a lasso and ignores redraw echoes without geometry", () => {
    show();
    act(() => handlers().onSelected({ points: [{ customdata: 2 }] }));
    expect(screen.getByTestId("sel")).toHaveTextContent(/^$/);
    act(() =>
      handlers().onSelected({ lassoPoints: { x: [], y: [] }, points: [{ customdata: 2 }, {}] }),
    );
    expect(screen.getByTestId("sel")).toHaveTextContent("w2");
    act(() => handlers().onDeselect());
    expect(screen.getByTestId("sel")).toHaveTextContent(/^$/);
  });

  it("selects the clicked point and notes rows it cannot plot", () => {
    show();
    act(() => handlers().onClick({ points: [{ customdata: 0 }] }));
    expect(screen.getByTestId("sel")).toHaveTextContent("w0");
    expect(screen.getByText("1 row lacks Signal")).toBeInTheDocument();
  });

  it("reuses the plotted arrays when only the selection changes", () => {
    show();
    const { x, text } = drawn().data[0];
    fireEvent.click(screen.getByRole("button", { name: "external" }));
    expect(drawn().data[0].selectedpoints).toEqual([0]);
    expect(drawn().data[0].x).toBe(x);
    expect(drawn().data[0].text).toBe(text);
  });

  it("drops its lasso outline when the selection changes elsewhere, keeping zoom", () => {
    show();
    lasso(2);
    const own = drawn().layout.selectionrevision;
    fireEvent.click(screen.getByRole("button", { name: "external" }));
    const after = drawn().layout.selectionrevision;
    expect(after).not.toBe(own);
    expect(drawn().layout.uirevision).toBe("p1");
    // The plot's own lasso keeps its outline.
    lasso(0, 2);
    expect(screen.getByTestId("sel")).toHaveTextContent("w0,w2");
    expect(drawn().layout.selectionrevision).toBe(after);
  });

  it("keeps untested compounds on a selectable strip and counts measured pairs", () => {
    const pair = { ...panel, x: "dr:y:p", y: "dr:x:p" };
    render(
      <WorkbenchProvider initialPanels={[pair]}>
        <ScatterPanel panel={pair} ds={crossProtocol} />
        <Selection />
      </WorkbenchProvider>,
    );
    expect(
      screen.getByText("1 measured pair · 1 not tested in Counter · 1 no value"),
    ).toBeInTheDocument();
    expect(drawn().data.at(-1)).toMatchObject({ xaxis: "x2", customdata: [1, 2] });
    lasso(1);
    expect(screen.getByTestId("sel")).toHaveTextContent("m2");
  });
});
