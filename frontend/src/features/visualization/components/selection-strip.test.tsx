import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it } from "vitest";
import type { Filter } from "../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { SelectionStrip } from "./selection-strip";

// 15 wells; plate B (wells 9–11) is filtered out.
const plates = [...Array(9).fill("A"), "B", "B", "B", "A", "A", "A"];
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 15,
  row_ids: plates.map((_, i) => `w${i}`),
  columns: [{ key: "plate", label: "Plate", kind: "category", provenance: {} }],
  values: { plate: plates },
};
const onlyA: Filter = {
  id: "f1",
  kind: "category",
  key: "plate",
  values: ["A"],
  includeMissing: false,
};
const twelve = ds.row_ids.slice(0, 12);

function Seed({ ids }: { ids: string[] }) {
  const setSelection = useWorkbench((s) => s.setSelection);
  // biome-ignore lint/correctness/useExhaustiveDependencies: seed once on mount
  useEffect(() => setSelection(ids), []);
  return null;
}

function Filters() {
  const filters = useWorkbench((s) => s.filters);
  return <p data-testid="filters">{filters.map((f) => f.kind).join(",")}</p>;
}

const show = (ids: string[], data: Dataset = ds) =>
  render(
    <WorkbenchProvider initialPanels={[]} initialFilters={[onlyA]}>
      <Seed ids={ids} />
      <SelectionStrip ds={data} />
      <Filters />
    </WorkbenchProvider>,
  );

describe("SelectionStrip", () => {
  it("counts the selected wells the filters show and hide", () => {
    show(twelve);
    expect(screen.getByRole("status")).toHaveTextContent(
      "12 wells selected · 9 visible · 3 hidden",
    );
  });

  it("counts in the level's noun", () => {
    show(twelve, { ...ds, level: "compounds" });
    expect(screen.getByRole("status")).toHaveTextContent("12 compounds selected");
  });

  it("is absent with nothing selected", () => {
    show([]);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("Clear empties the selection", () => {
    show(twelve);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("Filter to selection turns the selection into a filter", () => {
    show(twelve);
    fireEvent.click(screen.getByRole("button", { name: "Filter to selection" }));
    expect(screen.getByTestId("filters")).toHaveTextContent("category,rows");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
