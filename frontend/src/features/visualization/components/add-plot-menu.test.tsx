import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { dataset } from "../lib/traces/test-fixtures";
import { WorkbenchProvider } from "../store/workbench-context";
import { AddPlotMenu } from "./add-plot-menu";

describe("AddPlotMenu", () => {
  it("wraps a disabled item's reason inside a fixed-width menu instead of cutting it off", () => {
    render(
      <WorkbenchProvider initialPanels={[]}>
        <AddPlotMenu ds={dataset({ well_order: [1, 2], y: [3, 4] })} />
      </WorkbenchProvider>,
    );
    fireEvent.keyDown(screen.getByRole("button", { name: /Add plot/ }), { key: "Enter" });
    // jsdom has no layout: a fixed menu width plus a wrapping reason is what keeps it whole.
    expect(screen.getByRole("menu")).toHaveClass("w-64");
    const reason = screen.getByText("Add R-groups first: Add columns → R-groups…");
    expect(reason).toHaveClass("whitespace-normal");
  });
});
