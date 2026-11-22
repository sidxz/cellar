import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectionHeader } from "./selection-header";

/** A stand-in for the grid's API: `rows` with whether each is visible and ticked. */
function fakeApi(rows: { visible: boolean; selected: boolean }[]) {
  const node = (r: (typeof rows)[number]) => ({ isSelected: () => r.selected });
  return {
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    getSelectedNodes: () => rows.filter((r) => r.selected),
    getDisplayedRowCount: () => rows.filter((r) => r.visible).length,
    forEachNode: (fn: (n: unknown) => void) => {
      for (const r of rows) fn(node(r));
    },
    forEachNodeAfterFilter: (fn: (n: unknown) => void) => {
      for (const r of rows) if (r.visible) fn(node(r));
    },
    selectAll: vi.fn(),
    deselectAll: vi.fn(),
  };
}

function renderHeader(api: ReturnType<typeof fakeApi>) {
  render(<SelectionHeader api={api as never} />);
  return api;
}

describe("SelectionHeader", () => {
  const rows = [
    { visible: true, selected: false },
    { visible: true, selected: false },
    { visible: false, selected: false },
  ];

  it("ticks every visible row from its box, and only those", () => {
    const api = renderHeader(fakeApi(rows));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all 2 visible rows" }));
    expect(api.deselectAll).toHaveBeenCalled();
    expect(api.selectAll).toHaveBeenCalledWith("filtered");
  });

  it("offers every visible row, every row in the table, or none", () => {
    const api = renderHeader(fakeApi(rows));
    fireEvent.keyDown(screen.getByRole("button", { name: "Selection options" }), { key: "Enter" });
    expect(screen.getByRole("menuitem", { name: "Select all 2 visible" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "Select all 3 in the table" }));
    expect(api.selectAll).toHaveBeenCalledWith("all");
  });

  it("clears from its box once anything is ticked, and shows some-not-all as a dash", () => {
    const api = renderHeader(
      fakeApi([
        { visible: true, selected: true },
        { visible: true, selected: false },
      ]),
    );
    const box = screen.getByRole("checkbox", { name: "Clear selection" });
    expect(box).toHaveAttribute("data-state", "indeterminate");
    fireEvent.click(box);
    expect(api.deselectAll).toHaveBeenCalled();
    expect(api.selectAll).not.toHaveBeenCalled();
  });

  it("is ticked when exactly the visible rows are", () => {
    renderHeader(
      fakeApi([
        { visible: true, selected: true },
        { visible: false, selected: false },
      ]),
    );
    expect(screen.getByRole("checkbox", { name: "Clear selection" })).toHaveAttribute(
      "data-state",
      "checked",
    );
  });
});
