import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_SELECTION, type SelectionState, holderOrder } from "../lib/curve-selection";
import type { RunCurves } from "../types";
import { PositionSelector } from "./position-selector";

type Position = RunCurves["positions"][number];

function position(id: string, row: string, column: number, wellType = "sample"): Position {
  return {
    well_id: id,
    position: `${row}${column}`,
    row,
    column,
    well_type: wellType,
    registration_number: null,
    position_label: `Position ${row}${column}`,
    label: null,
    note: null,
  };
}

const cassette = { kind: "cassette", rows: 1, columns: 5, label: "Holder of 5" };
const cassettePositions = [
  position("w1", "A", 1, "reference"),
  position("w2", "A", 2, "blank"),
  position("w5", "A", 5),
];

function renderSelector(
  overrides: Partial<Parameters<typeof PositionSelector>[0]> = {},
  selection: SelectionState = EMPTY_SELECTION,
) {
  const onChange = vi.fn();
  const onFocus = vi.fn();
  render(
    <PositionSelector
      holder={cassette}
      positions={cassettePositions}
      selection={selection}
      orderedIds={holderOrder(overrides.positions ?? cassettePositions).map((p) => p.well_id)}
      onChange={onChange}
      focusedId={null}
      onFocus={onFocus}
      {...overrides}
    />,
  );
  return { onChange, onFocus };
}

describe("PositionSelector", () => {
  it("draws every slot of a cassette with gaps and disables the empty ones", () => {
    renderSelector();
    expect(screen.getAllByRole("button", { name: /Position/ })).toHaveLength(3);
    expect(screen.getAllByTestId("empty-slot")).toHaveLength(2);
    expect(screen.getAllByTestId("holder-row")).toHaveLength(1);
    expect(screen.getByText("0 of 3 selected")).toBeInTheDocument();
  });

  it("draws a plate holder as rows by columns", () => {
    renderSelector({
      holder: { kind: "plate", rows: 2, columns: 3, label: "Plate of 6" },
      positions: [position("a1", "A", 1), position("b2", "B", 2)],
    });
    const rows = screen.getAllByTestId("holder-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[1]).getByRole("button", { name: "Position B2" })).toBeInTheDocument();
    expect(within(rows[1]).getAllByTestId("empty-slot")).toHaveLength(2);
  });

  it("shows the column number in an empty cassette slot", () => {
    renderSelector();
    const empty = screen.getAllByTestId("empty-slot");
    expect(empty.map((e) => e.textContent)).toEqual(["3", "4"]);
  });

  it("shows row letters and column numbers around a plate grid", () => {
    renderSelector({
      holder: { kind: "plate", rows: 2, columns: 3, label: "Plate of 6" },
      positions: [position("a1", "A", 1)],
    });
    for (const h of ["A", "B", "1", "2", "3"]) {
      expect(screen.getByText(h)).toBeInTheDocument();
    }
  });

  it("passes shift and meta keys to onChange as range and toggle", () => {
    const anchored = { selected: new Set(["w1"]), anchor: "w1" };
    const { onChange } = renderSelector({}, anchored);
    fireEvent.click(screen.getByRole("button", { name: "Position A5" }), { shiftKey: true });
    expect([...onChange.mock.calls[0][0].selected].sort()).toEqual(["w1", "w2", "w5"]);
    fireEvent.click(screen.getByRole("button", { name: "Position A2" }), { metaKey: true });
    expect([...onChange.mock.calls[1][0].selected].sort()).toEqual(["w1", "w2"]);
  });

  it("selects all and none", () => {
    const { onChange } = renderSelector();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect([...onChange.mock.calls[0][0].selected]).toEqual(["w1", "w2", "w5"]);
    fireEvent.click(screen.getByRole("button", { name: "None" }));
    expect(onChange.mock.calls[1][0].selected.size).toBe(0);
  });

  it("marks reference and blank positions", () => {
    renderSelector();
    expect(screen.getByTitle("Reference")).toBeInTheDocument();
    expect(screen.getByTitle("Blank")).toBeInTheDocument();
  });

  it("reports hover as focus and outlines the focused slot", () => {
    const { onFocus } = renderSelector({ focusedId: "w5" });
    const slot = screen.getByRole("button", { name: "Position A5" });
    expect(slot).toHaveAttribute("data-focused", "true");
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Position A1" }));
    expect(onFocus).toHaveBeenLastCalledWith("w1");
    fireEvent.mouseLeave(screen.getByRole("button", { name: "Position A1" }));
    expect(onFocus).toHaveBeenLastCalledWith(null);
  });

  it("dims a filtered-out position and does not let it be clicked", () => {
    const { onChange } = renderSelector({ disabledIds: new Set(["w2"]) });
    const slot = screen.getByRole("button", { name: "Position A2" });
    expect(slot).toBeDisabled();
    fireEvent.click(slot);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("leaves filtered-out positions out of All and out of a shift range", () => {
    const anchored = { selected: new Set(["w1"]), anchor: "w1" };
    const { onChange } = renderSelector({ disabledIds: new Set(["w2"]) }, anchored);
    fireEvent.click(screen.getByRole("button", { name: "Position A5" }), { shiftKey: true });
    expect([...onChange.mock.calls[0][0].selected].sort()).toEqual(["w1", "w5"]);
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect([...onChange.mock.calls[1][0].selected].sort()).toEqual(["w1", "w5"]);
  });

  it("adds its group to a selection from another group with All and removes only its group with None", () => {
    const other = { selected: new Set(["x9", "w1"]), anchor: null };
    const { onChange } = renderSelector({}, other);
    expect(screen.getByText("1 of 3 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect([...onChange.mock.calls[0][0].selected].sort()).toEqual(["w1", "w2", "w5", "x9"]);
    fireEvent.click(screen.getByRole("button", { name: "None" }));
    expect([...onChange.mock.calls[1][0].selected]).toEqual(["x9"]);
  });

  it("selects a shift range through the ids of other groups", () => {
    const anchored = { selected: new Set(["x1"]), anchor: "x1" };
    const { onChange } = renderSelector({ orderedIds: ["x1", "x2", "w1", "w2", "w5"] }, anchored);
    fireEvent.click(screen.getByRole("button", { name: "Position A2" }), { shiftKey: true });
    expect([...onChange.mock.calls[0][0].selected].sort()).toEqual(["w1", "w2", "x1", "x2"]);
  });

  it("shows the heading it is given", () => {
    renderSelector({ heading: <a href="/somewhere">A run heading</a> });
    expect(screen.getByRole("link", { name: "A run heading" })).toBeInTheDocument();
  });
});
