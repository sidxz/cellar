import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { crossProtocol, singleProtocol } from "../../lib/cross-protocol-fixture";
import { dataset, panel } from "../../lib/traces/test-fixtures";
import { WorkbenchProvider, useWorkbench } from "../../store/workbench-context";
import type { PanelConfig, PanelPatch } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { OverlaySection, parseNumberList } from "./overlay-section";

const Y = "rd:s:raw";
const P = "rd:a:raw:p";

const wells = dataset({
  well_order: [1, 2],
  dose: [0.1, 1],
  [Y]: [1, 2],
  plate: ["1", "2"],
  plate_id: ["a", "b"],
  well_type: ["sample", "negative_control"],
});
const withUnit = (ds: Dataset, key: string, unit: string): Dataset => ({
  ...ds,
  columns: ds.columns.map((c) => (c.key === key ? { ...c, unit } : c)),
});
const runs: Dataset = {
  ...dataset({ run_date: ["2026-01-01", "2026-01-02"], [Y]: [7.4, 7.5] }),
  level: "runs",
};
const compounds: Dataset = (() => {
  const ds = dataset({ [P]: [7, 6], logp: [2, 3], molecular_weight: [300, 310] });
  return {
    ...ds,
    level: "compounds",
    columns: ds.columns.map((c) =>
      c.key === P ? { ...c, provenance: { ...c.provenance, stat: null, aggregation: "p" } } : c,
    ),
  };
})();

const scatter = (patch: PanelPatch = {}) => panel("scatter", { x: "well_order", y: Y, ...patch });

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

function show(p: PanelConfig, ds: Dataset = wells) {
  return render(
    <WorkbenchProvider initialPanels={[p]}>
      <OverlaySection ds={ds} panelId={p.id} />
      <Probe />
    </WorkbenchProvider>,
  );
}

const undo = () => fireEvent.click(screen.getByRole("button", { name: "Undo" }));
/** Type ``text`` and leave the input, as a user would. */
function enter(input: HTMLElement, text: string) {
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

describe("OverlaySection", () => {
  it("shows the overlays a wells scatter can draw, disabled ones with their reason", () => {
    show(scatter({ x: "dose" }));
    expect(screen.getByRole("heading", { name: "Overlays" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Control bands (mean ± 3 SD)" })).toBeEnabled();
    const z = screen.getByRole("checkbox", { name: "Z′ per plate (stored)" });
    expect(z).toBeDisabled();
    expect(z).toHaveAccessibleDescription("Split by Plate to show stored Z′");
    const driftBand = screen.getByRole("radio", { name: "Band per plate row/column" });
    expect(driftBand).toBeDisabled();
    expect(driftBand).toHaveAccessibleDescription("Drift bands need X = Well order or Column");
    expect(screen.getByRole("radio", { name: "Trend line" })).toBeEnabled();
    expect(screen.getByRole("spinbutton", { name: "Reference line" })).toBeEnabled();
    expect(screen.queryByRole("radiogroup", { name: "Control limits" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "LipE guides" })).not.toBeInTheDocument();
  });

  it("shows nothing for a plot that can draw no overlay", () => {
    const { container } = show(panel("histogram", { x: Y }));
    expect(container.querySelector("section")).toBeNull();
  });

  it("toggles control bands in one undoable step", () => {
    show(scatter());
    fireEvent.click(screen.getByRole("checkbox", { name: "Control bands (mean ± 3 SD)" }));
    expect(state().history).toBe(1);
    expect(state().panel.overlays).toEqual({ bands: true });
    undo();
    expect(state().history).toBe(0);
    expect(state().panel.overlays).toBeUndefined();
    expect(screen.getByRole("checkbox", { name: "Control bands (mean ± 3 SD)" })).not.toBeChecked();
  });

  it("picks a drift mode and clears it with None", () => {
    show(scatter({ overlays: { bands: true } }));
    fireEvent.click(screen.getByRole("radio", { name: "Band per plate row/column" }));
    expect(state().panel.overlays).toEqual({ bands: true, drift: "band" });
    fireEvent.click(screen.getByRole("radio", { name: "None" }));
    expect(state().panel.overlays).toEqual({ bands: true });
    expect(state().history).toBe(2);
  });

  it("starts the reference line empty", () => {
    show(scatter());
    expect(screen.getByRole("spinbutton", { name: "Reference line" })).toHaveValue(null);
  });

  it("starts entered limits and LipE values empty", () => {
    const { unmount } = show(scatter({ x: "run_date" }), runs);
    fireEvent.click(screen.getByRole("radio", { name: "Entered" }));
    expect(screen.getByRole("spinbutton", { name: "Lower" })).toHaveValue(null);
    expect(screen.getByRole("spinbutton", { name: "Upper" })).toHaveValue(null);
    expect(state().history).toBe(0);
    unmount();
    show(scatter({ x: "logp", y: P }), compounds);
    expect(screen.getByRole("textbox", { name: "LipE guides" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "LipE guides" })).toHaveAttribute(
      "placeholder",
      "e.g. 3, 5",
    );
  });

  it("commits the reference line when left, says it is display only, and clears when emptied", () => {
    show(scatter(), withUnit(wells, Y, "%"));
    const ref = screen.getByRole("spinbutton", { name: "Reference line" });
    expect(ref).toHaveAccessibleDescription("% Display only — hit criteria are unchanged");
    ref.focus();
    fireEvent.change(ref, { target: { value: "3" } });
    fireEvent.change(ref, { target: { value: "30" } });
    expect(state().history).toBe(0);
    fireEvent.keyDown(ref, { key: "Enter" });
    expect(state().history).toBe(1);
    expect(state().panel.overlays).toEqual({ refLine: 30 });

    const again = screen.getByRole("spinbutton", { name: "Reference line" });
    expect(again).toHaveValue(30);
    enter(again, "30");
    expect(state().history).toBe(1);
    enter(again, "");
    expect(state().history).toBe(2);
    expect(state().panel.overlays).toEqual({});
  });

  it("commits LipE guides on blur in one undo entry", () => {
    show(scatter({ x: "logp", y: P }), compounds);
    enter(screen.getByRole("textbox", { name: "LipE guides" }), "3, 5");
    expect(state().history).toBe(1);
    expect(state().panel.overlays).toEqual({ lipe: [3, 5] });
    undo();
    expect(state().panel.overlays).toBeUndefined();
    expect(screen.getByRole("textbox", { name: "LipE guides" })).toHaveValue("");
  });

  it("says why LipE guides cannot be drawn yet", () => {
    show(scatter({ x: "molecular_weight", y: P }), compounds);
    const lipe = screen.getByRole("textbox", { name: "LipE guides" });
    expect(lipe).toBeDisabled();
    expect(lipe).toHaveAccessibleDescription("Set X to logP");
  });

  it("takes selectivity folds when protocols are compared, starting empty", () => {
    show(scatter({ x: "dr:y:p", y: "dr:x:p" }), crossProtocol);
    const folds = screen.getByRole("textbox", { name: "Selectivity folds" });
    expect(folds).toHaveValue("");
    expect(folds).toHaveAttribute("placeholder", "e.g. 10, 100");
    enter(folds, "10, 100");
    expect(state().panel.overlays).toEqual({ selectivity: [10, 100] });
    expect(state().history).toBe(1);
  });

  it("says why selectivity guides cannot be drawn yet", () => {
    show(scatter({ x: "sel:dr:x:p|dr:y:p", y: "dr:x:p" }), crossProtocol);
    const folds = screen.getByRole("textbox", { name: "Selectivity folds" });
    expect(folds).toBeDisabled();
    expect(folds).toHaveAccessibleDescription("Plot a p-potency from each protocol on X and Y");
  });

  it("offers no selectivity folds for one protocol", () => {
    show(scatter({ x: "dr:y:p", y: "dr:x:p" }), singleProtocol);
    expect(screen.queryByRole("textbox", { name: "Selectivity folds" })).not.toBeInTheDocument();
  });

  it("draws control limits from plotted points or entered ones, refusing Lower ≥ Upper", () => {
    show(scatter({ x: "run_date" }), runs);
    fireEvent.click(screen.getByRole("radio", { name: "From plotted points" }));
    expect(state().panel.overlays).toEqual({ limits: { mode: "plotted" } });

    fireEvent.click(screen.getByRole("radio", { name: "Entered" }));
    expect(state().history).toBe(1);
    const lower = screen.getByRole("spinbutton", { name: "Lower" });
    const upper = screen.getByRole("spinbutton", { name: "Upper" });
    enter(lower, "8");
    enter(upper, "7");
    expect(screen.getByRole("alert")).toHaveTextContent("Lower must be below Upper");
    expect(upper).toHaveAttribute("aria-invalid", "true");
    expect(state().history).toBe(1);
    expect(state().panel.overlays).toEqual({ limits: { mode: "plotted" } });

    enter(lower, "7");
    enter(upper, "7.8");
    expect(state().history).toBe(2);
    expect(state().panel.overlays).toEqual({ limits: { mode: "entered", lower: 7, upper: 7.8 } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Off" }));
    expect(state().panel.overlays).toEqual({});
    expect(state().history).toBe(3);
  });

  it("explains why control limits need Run date on X", () => {
    show(scatter({ x: Y }), runs);
    const group = screen.getByRole("radiogroup", { name: "Control limits" });
    expect(group).toHaveAccessibleDescription("Set X to Run date");
    expect(screen.getByRole("radio", { name: "Off" })).toBeDisabled();
  });
});

describe("parseNumberList", () => {
  it("reads comma or space separated numbers, dropping the rest", () => {
    expect(parseNumberList("3, x 5")).toEqual([3, 5]);
    expect(parseNumberList(" 2.5,-1 ")).toEqual([2.5, -1]);
    expect(parseNumberList("")).toEqual([]);
  });
});
