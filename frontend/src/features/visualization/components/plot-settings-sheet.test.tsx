import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { MAX_CATEGORIES } from "../lib/traces/common";
import { dataset, matrixWells, panel } from "../lib/traces/test-fixtures";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { PanelConfig, PanelPatch } from "../store/workbench-store";
import type { EditField } from "./panels/panel-frame";
import { PlotSettingsSheet } from "./plot-settings-sheet";

// Radix Popover / cmdk need these in jsdom.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const Y = "rd:s:raw";
const ds = dataset({
  well_order: [1, 2, 3, 4],
  [Y]: [0, 3, 6, 9],
  plate: ["1", "1", "2", "2"],
  well_type: ["sample", "sample", "blank", "sample"],
});
const scatter = (patch: PanelPatch = {}) =>
  panel("scatter", {
    x: "well_order",
    y: Y,
    ...patch,
    appearance: { colorBy: "well_type", ...patch.appearance },
  });

function Probe() {
  const p = useWorkbench((s) => s.panels[0]);
  const history = useWorkbench((s) => s.past.length);
  const undo = useWorkbench((s) => s.undo);
  return (
    <>
      <output data-testid="state">{JSON.stringify({ history, panel: p })}</output>
      <button type="button" onClick={undo}>
        Undo
      </button>
    </>
  );
}
const state = (): { history: number; panel: PanelConfig } =>
  JSON.parse(screen.getByTestId("state").textContent ?? "{}");

function show(p: PanelConfig, focusField?: EditField, data = ds) {
  const onClose = vi.fn();
  render(
    <WorkbenchProvider initialPanels={[p]}>
      <PlotSettingsSheet ds={data} panelId={p.id} focusField={focusField} onClose={onClose} />
      <Probe />
    </WorkbenchProvider>,
  );
  return onClose;
}

describe("PlotSettingsSheet", () => {
  it("changes color-by in one undoable step", () => {
    show(scatter());
    fireEvent.click(screen.getByRole("combobox", { name: "Color" }));
    fireEvent.click(screen.getByRole("option", { name: "plate" }));
    expect(state().history).toBe(1);
    expect(state().panel.appearance.colorBy).toBe("plate");

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(state().history).toBe(0);
    expect(state().panel.appearance.colorBy).toBe("well_type");
  });

  it("opens at the control a header chip named, and closes on Escape", () => {
    const onClose = show(scatter({ appearance: { splitBy: "plate" } }), "splitBy");
    const split = screen.getByRole("combobox", { name: "Split by" });
    expect(split).toHaveFocus();
    fireEvent.keyDown(split, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("commits a bin cut-off when the input is left, not per keystroke", () => {
    show(scatter({ appearance: { colorBy: Y, colorMode: "bins" } }));
    const first = screen.getByRole("spinbutton", { name: "Cut-off 1" });
    expect(first).toHaveValue(3);
    fireEvent.change(first, { target: { value: "2" } });
    fireEvent.change(first, { target: { value: "2.5" } });
    expect(state().history).toBe(0);
    fireEvent.blur(first);
    expect(state().history).toBe(1);
    expect(state().panel.appearance.colorBins).toEqual([2.5, 6]);

    fireEvent.click(screen.getByRole("button", { name: "Add bin" }));
    expect(state().panel.appearance.colorBins).toEqual([2.5, 6, 7.5]);
    fireEvent.click(screen.getByRole("button", { name: "Remove cut-off 1" }));
    expect(state().panel.appearance.colorBins).toEqual([6, 7.5]);
    expect(state().history).toBe(3);
  });

  it("switches plot type keeping the measured field", () => {
    show(scatter());
    fireEvent.click(screen.getByRole("button", { name: "Box" }));
    expect(state().history).toBe(1);
    expect(state().panel).toMatchObject({ type: "box", y: Y, category: "well_type" });
  });

  it("offers log toggles only on the axes the plot draws on a log scale", () => {
    show(scatter());
    expect(screen.getByRole("checkbox", { name: "Log X" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Log Y" }));
    expect(state().panel.logY).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Histogram" }));
    expect(screen.queryByRole("checkbox", { name: /Log/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Box" }));
    expect(screen.queryByRole("checkbox", { name: "Log X" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Log Y" })).toBeInTheDocument();
  });

  it("disables a group field with more values than bars or boxes can show, saying why", () => {
    const rows = Array.from({ length: MAX_CATEGORIES + 1 }, (_, i) => i);
    const many = dataset({
      [Y]: rows,
      plate: rows.map((i) => String(i % 2)),
      compound: rows.map((i) => `CEL-${i}`),
    });
    show(panel("bar", { category: "plate" }), undefined, many);
    fireEvent.click(screen.getByRole("combobox", { name: "Group" }));
    const compound = screen.getByRole("option", { name: /compound/ });
    expect(compound).toHaveAttribute("aria-disabled", "true");
    expect(compound).toHaveTextContent("501 values; at most 500 groups can be shown");
    fireEvent.click(compound);
    expect(state().panel.category).toBe("plate");
  });

  it("offers Run date as a scatter X, without a log toggle", () => {
    const dated = dataset({
      ...ds.values,
      run_date: ["2026-01-01", "2026-01-01", "2026-01-02", null],
    });
    show(scatter({ logX: true }), undefined, dated);
    fireEvent.click(screen.getByRole("combobox", { name: "X" }));
    fireEvent.click(screen.getByRole("option", { name: "run_date" }));
    expect(state().history).toBe(1);
    expect(state().panel).toMatchObject({ x: "run_date", logX: false });
    expect(screen.queryByRole("checkbox", { name: "Log X" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Histogram" }));
    fireEvent.click(screen.getByRole("combobox", { name: "X" }));
    expect(screen.queryByRole("option", { name: "run_date" })).not.toBeInTheDocument();
  });

  it("ends with the overlays the plot can draw, none on a histogram", () => {
    show(scatter());
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.at(-1)).toBe("Overlays");
    expect(screen.getByRole("checkbox", { name: "Control bands (mean ± 3 SD)" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Histogram" }));
    expect(screen.queryByRole("heading", { name: "Overlays" })).not.toBeInTheDocument();
  });

  it("names the opacity slider", () => {
    show(scatter());
    expect(screen.getByRole("slider", { name: "Opacity" })).toBeInTheDocument();
  });

  it("edits an R-group matrix's rows, columns, value and aggregate", () => {
    const m = panel("rgroup-matrix", { category: "chem:rg1:R1", x: "chem:rg1:R2", y: "rd:s:raw" });
    show(m, undefined, matrixWells());
    expect(screen.queryByRole("group", { name: "Plot type" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Log/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Rows")).toHaveTextContent("R1");
    expect(screen.getByLabelText("Columns")).toHaveTextContent("R2");
    fireEvent.click(screen.getByRole("button", { name: "Mean" }));
    expect(state().panel).toMatchObject({ agg: "mean", category: "chem:rg1:R1" });
  });
});
