import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkbenchProvider } from "../../store/workbench-context";
import { DEFAULT_APPEARANCE, type PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { PanelFrame } from "./panel-frame";

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

const show = (onEdit = vi.fn()) => {
  render(
    <WorkbenchProvider initialPanels={[panel]}>
      <PanelFrame panel={panel} ds={ds} onEdit={onEdit}>
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
});
