import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import type { ExternalToast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Filter } from "../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";

type ToastFor = (created: { id: string; name: string }) => ExternalToast;
const state = vi.hoisted(() => ({
  canEdit: true,
  mutate: vi.fn(),
  push: vi.fn(),
  toastFor: undefined as ToastFor | undefined,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: state.push }) }));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => state.canEdit }));
vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCreateCollection: (toastFor: ToastFor) => {
    state.toastFor = toastFor;
    return { mutate: state.mutate, isPending: false };
  },
}));

import { SaveCollectionButton } from "./save-collection-dialog";

// w0–w8: 9 sample wells on plate A covering m1–m8 (m8 twice); w9/w10: controls on A
// (w10 holds a reference compound); w11–w13: samples on plate B, filtered out.
const wellType = [...Array(9).fill("sample"), "negative_control", "positive_control"];
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 14,
  row_ids: Array.from({ length: 14 }, (_, i) => `w${i}`),
  columns: [
    { key: "plate", label: "Plate", kind: "category", provenance: {} },
    { key: "well_type", label: "Well type", kind: "category", provenance: {} },
    { key: "molecule_id", label: "Molecule", kind: "text", provenance: {}, hidden: true },
  ],
  values: {
    plate: [...Array(11).fill("A"), "B", "B", "B"],
    well_type: [...wellType, "sample", "sample", "sample"],
    molecule_id: [
      ...["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m8"],
      null,
      "mRef",
      ...["m9", "m10", "m11"],
    ],
  },
};
const onlyA: Filter = {
  id: "a",
  kind: "category",
  key: "plate",
  values: ["A"],
  includeMissing: false,
};

function Seed({ ids }: { ids: string[] }) {
  const setSelection = useWorkbench((s) => s.setSelection);
  // biome-ignore lint/correctness/useExhaustiveDependencies: seed once on mount
  useEffect(() => setSelection(ids), []);
  return null;
}

const show = (ids: string[]) =>
  render(
    <WorkbenchProvider initialPanels={[]} initialFilters={[onlyA]}>
      <Seed ids={ids} />
      <SaveCollectionButton ds={ds} />
    </WorkbenchProvider>,
  );

beforeEach(() => {
  state.canEdit = true;
  state.mutate.mockReset();
  state.push.mockReset();
});

describe("SaveCollectionButton", () => {
  it("counts the compounds of the visible selected wells", () => {
    show(ds.row_ids.slice(0, 9).concat("w11", "w12", "w13"));
    expect(screen.getByRole("button", { name: "Save 8 compounds…" })).toBeEnabled();
  });

  it("is disabled when only control wells are selected", () => {
    show(["w9", "w10"]);
    expect(screen.getByRole("button", { name: "Save 0 compounds…" })).toBeDisabled();
  });

  it("is hidden for viewers", () => {
    state.canEdit = false;
    show([]);
    expect(screen.queryByRole("button", { name: /Save/ })).not.toBeInTheDocument();
  });
});

describe("SaveCollectionDialog", () => {
  it("saves the filtered rows' compounds without controls, then links to the collection", () => {
    show([]);
    fireEvent.click(screen.getByRole("button", { name: "Save 8 compounds…" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("8 compounds");
    const save = screen.getByRole("button", { name: "Save collection" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: " NadD hits " } });
    state.mutate.mockImplementation((_body, opts) =>
      opts.onSuccess({ id: "c1", name: "NadD hits" }),
    );
    fireEvent.click(save);

    expect(state.mutate).toHaveBeenCalledWith(
      { name: "NadD hits", molecule_ids: ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8"] },
      expect.anything(),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const toast = state.toastFor?.({ id: "c1", name: "NadD hits" });
    const action = toast?.action as { label: string; onClick: () => void };
    expect(action.label).toBe("Open collection");
    action.onClick();
    expect(state.push).toHaveBeenCalledWith("/collections/c1");
  });

  it("says when the compounds come from the selection", () => {
    show(["w0", "w1", "w9"]);
    fireEvent.click(screen.getByRole("button", { name: "Save 2 compounds…" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("2 compounds from your selection");
  });
});
