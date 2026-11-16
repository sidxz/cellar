import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { withSeenLabels } from "../../lib/traces/common";
import { WorkbenchProvider } from "../../store/workbench-context";
import { DEFAULT_APPEARANCE, type PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { PanelFrame, panelTitle } from "./panel-frame";

const col = (key: string, label: string) => ({
  key,
  label,
  kind: "number" as const,
  provenance: {},
});
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 0,
  row_ids: [],
  columns: [
    col("well_order", "Well order"),
    col("rd:s:raw", "Signal (AU)"),
    { ...col("plate", "Plate"), kind: "category" },
    { ...col("well_type", "Well type"), kind: "category" },
  ],
  values: {},
};
const panel: PanelConfig = {
  id: "p1",
  type: "scatter",
  x: "well_order",
  y: "rd:s:raw",
  logY: true,
  appearance: {
    ...DEFAULT_APPEARANCE,
    splitBy: "plate",
    colorBy: "well_type",
    shapeBy: "well_type",
  },
};

const show = (onEdit = vi.fn(), p = panel) => {
  render(
    <WorkbenchProvider initialPanels={[p]}>
      <PanelFrame panel={p} ds={ds} onEdit={onEdit}>
        <p>plot</p>
      </PanelFrame>
    </WorkbenchProvider>,
  );
  return onEdit;
};

describe("PanelFrame", () => {
  it("titles the panel and opens the editor from the button and each chip", () => {
    const onEdit = show();
    expect(screen.getByText("Signal (AU) by Well order")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit plot" }));
    expect(onEdit).toHaveBeenLastCalledWith("p1");
    fireEvent.click(screen.getByRole("button", { name: "Y Signal (AU) (log)" }));
    expect(onEdit).toHaveBeenLastCalledWith("p1", "y");
    fireEvent.click(screen.getByRole("button", { name: "Split Plate" }));
    expect(onEdit).toHaveBeenLastCalledWith("p1", "splitBy");
    fireEvent.click(screen.getByRole("button", { name: "Color + shape Well type" }));
    expect(onEdit).toHaveBeenLastCalledWith("p1", "colorBy");
  });

  it("shows chips only for the fields the plot type draws", () => {
    show(vi.fn(), { ...panel, type: "bar", agg: "count", category: "plate" });
    expect(screen.getByRole("button", { name: "Group Plate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(Y|X|Split|Color)/ })).not.toBeInTheDocument();
  });

  it("names a field whose column has gone since by the label it last had", () => {
    const gone = { ...panel, x: "chem:clusters:x", y: "chem:clusters:y" };
    const seen = new Map([
      ["chem:clusters:x", "Cluster map X"],
      ["chem:clusters:y", "Cluster map Y"],
    ]);
    expect(panelTitle(ds, gone)).toBe("chem:clusters:y by chem:clusters:x");
    expect(panelTitle(withSeenLabels({ ...ds }, seen), gone)).toBe(
      "Cluster map Y by Cluster map X",
    );
  });
});
