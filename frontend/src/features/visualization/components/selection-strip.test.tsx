import type { Run } from "@/features/screening-assay/types";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Filter } from "../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";

const state = vi.hoisted(() => ({
  canEdit: true,
  mutateAsync: vi.fn(),
  success: vi.fn(),
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => state.canEdit }));
vi.mock("@/features/screening-assay/hooks/use-flag-outliers", () => ({
  useFlagOutliers: () => ({ mutateAsync: state.mutateAsync, isPending: false }),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: state.success,
  showWarning: vi.fn(),
}));

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

describe("SelectionStrip outlier flags", () => {
  // r1: wells a (flagged), b; r2 (approved): well c; a well-less row of r1.
  const wells: Dataset = {
    revision: "r",
    level: "wells",
    row_count: 4,
    row_ids: ["r1:a", "r1:b", "r2:c", "r1:m:mol:batch"],
    columns: [{ key: "plate", label: "Plate", kind: "category", provenance: {} }],
    values: {
      plate: ["A", "A", "A", "A"],
      "rd:x:raw": [1, 2, 3, 4],
      "rd:x:raw:outlier": ["outlier", null, null, null],
    },
  };
  const runs = [
    { id: "r1", status: "draft", is_locked: false },
    { id: "r2", status: "approved", is_locked: false },
  ] as Run[];
  const strip = (data: Dataset = wells) =>
    render(
      <WorkbenchProvider initialPanels={[]} initialFilters={[]}>
        <Seed ids={data.row_ids} />
        <SelectionStrip ds={data} runs={runs} />
      </WorkbenchProvider>,
    );

  beforeEach(() => {
    state.canEdit = true;
    state.mutateAsync.mockReset();
    state.mutateAsync.mockResolvedValue({
      wells_changed: 1,
      recalculated: true,
      compute_warning: null,
    });
  });

  it("flags the selected wells of runs the user can edit, with a reason", async () => {
    strip();
    fireEvent.click(screen.getByRole("button", { name: "Flag as outlier" }));
    expect(screen.getByText("1 well")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "bubble" } });
    fireEvent.click(
      screen.getAllByRole("button", { name: "Flag as outlier" }).at(-1) as HTMLElement,
    );
    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({
        runId: "r1",
        well_ids: ["b"],
        outlier: true,
        reason: "bubble",
      }),
    );
    expect(state.mutateAsync).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(state.success).toHaveBeenCalled());
  });

  it("removes the flag of the flagged ones", async () => {
    strip();
    fireEvent.click(screen.getByRole("button", { name: "Remove flag" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove outlier flag" }));
    await waitFor(() =>
      expect(state.mutateAsync).toHaveBeenCalledWith({
        runId: "r1",
        well_ids: ["a"],
        outlier: false,
        reason: null,
      }),
    );
  });

  it("offers nothing to a viewer, or above the Wells level", () => {
    state.canEdit = false;
    const { unmount } = strip();
    expect(screen.queryByRole("button", { name: "Flag as outlier" })).toBeNull();
    unmount();
    state.canEdit = true;
    strip({ ...wells, level: "compounds" });
    expect(screen.queryByRole("button", { name: "Flag as outlier" })).toBeNull();
  });
});
