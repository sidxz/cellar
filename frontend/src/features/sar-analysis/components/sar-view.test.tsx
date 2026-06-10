import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SarView } from "./sar-view";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const DECOMPOSITION_TWO_GROUPS: RGroupDecompositionResponse = {
  core_smiles: "c1ccccc1",
  rgroup_labels: ["R1", "R2"],
  assignments: [{ molecule_id: "m1", rgroups: { R1: "C", R2: "F" } }],
  unmatched_ids: ["m2"],
};

// One-group decomposition — heatmap is NOT valid here.
const DECOMPOSITION_ONE_GROUP: RGroupDecompositionResponse = {
  core_smiles: "c1ccccc1",
  rgroup_labels: ["R1"],
  assignments: [{ molecule_id: "m1", rgroups: { R1: "C" } }],
  unmatched_ids: ["m2"],
};

// Default fixture used by existing tests (kept at one R-group so legacy tests
// don't have to change their expectations).
const DECOMPOSITION = DECOMPOSITION_ONE_GROUP;

const molecules = [
  { id: "m1", structure: { smiles: "Cc1ccccc1" } } as never,
  { id: "m2", structure: { smiles: "Clc1ccccc1" } } as never,
];

const FIXED_COLOR_SPEC = {
  protocolId: "proto-1",
  column: "drc:rd-1",
  interceptKey: null,
  source: "dr_curve" as const,
  label: "EGFR · IC50",
};

const FIXED_ACTIVITY: Record<string, { value: number; unit: string; source: "dr_curve" }> = {
  m1: { value: 0.1, unit: "µM", source: "dr_curve" },
};

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Decomposition hook — `.mutate` is a spy, `.data` is the fixed fixture.
const mockMutate = vi.fn();
let _decompositionData: RGroupDecompositionResponse | undefined = DECOMPOSITION;
vi.mock("../hooks/use-rgroup-decomposition", () => ({
  useRGroupDecomposition: () => ({
    mutate: mockMutate,
    get data() {
      return _decompositionData;
    },
    isPending: false,
  }),
}));

// No handoff — the chemist picks a core via the picker.
vi.mock("../lib/sar-handoff", () => ({
  readSarHandoff: () => null,
}));

// Bulk-add goes through customInstance — record its calls.
const mockCustomInstance = vi.fn().mockResolvedValue({});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: unknown[]) => mockCustomInstance(...args),
}));

// Core picker stub — exposes a button that drives onCoreChange.
vi.mock("./rgroup-core-picker", () => ({
  RGroupCorePicker: ({ onCoreChange }: { onCoreChange: (s: string) => void }) => (
    <button type="button" data-testid="set-core" onClick={() => onCoreChange("c1ccccc1")}>
      set core
    </button>
  ),
}));

// Table stub — renders only when a decomposition is present; exposes a save hook.
vi.mock("./rgroup-table", () => ({
  RGroupTable: ({ onSaveSelection }: { onSaveSelection: (ids: string[]) => void }) => (
    <div data-testid="rgroup-table">
      <button type="button" data-testid="save-selection" onClick={() => onSaveSelection(["m1"])}>
        save
      </button>
    </div>
  ),
}));

// Heatmap stub.
vi.mock("./rgroup-heatmap", () => ({
  RGroupHeatmap: () => <div data-testid="rgroup-heatmap">heatmap</div>,
}));

// Color control stub — exposes an onChange trigger button.
let _colorControlOnChange: ((spec: typeof FIXED_COLOR_SPEC | null) => void) | null = null;
vi.mock("./rgroup-color-control", () => ({
  RGroupColorControl: ({
    onChange,
  }: {
    onChange: (spec: typeof FIXED_COLOR_SPEC | null) => void;
  }) => {
    _colorControlOnChange = onChange;
    return (
      <div data-testid="rgroup-color-control">
        <button
          type="button"
          data-testid="set-color-spec"
          onClick={() => onChange(FIXED_COLOR_SPEC)}
        >
          set color
        </button>
        <button type="button" data-testid="clear-color-spec" onClick={() => onChange(null)}>
          clear color
        </button>
      </div>
    );
  },
}));

// useSarActivity — return fixed activity by molecule; record call args.
const mockUseSarActivity = vi.fn().mockReturnValue({
  activityByMolecule: FIXED_ACTIVITY,
  isFetching: false,
});
vi.mock("../hooks/use-sar-activity", () => ({
  useSarActivity: (...args: unknown[]) => mockUseSarActivity(...args),
}));

// Save dialog stub — when open, exposes a button that fires onSave so the
// create → bulk-add flow can be driven from a test.
vi.mock("./save-selection-dialog", () => ({
  SaveSelectionDialog: ({
    open,
    onSave,
  }: {
    open: boolean;
    onSave: (a: { name: string; projectId: string | null; moleculeIds: string[] }) => Promise<void>;
  }) =>
    open ? (
      <button
        type="button"
        data-testid="confirm-save"
        onClick={() => onSave({ name: "Series A", projectId: null, moleculeIds: ["m1"] })}
      >
        confirm save
      </button>
    ) : null,
}));

// Create-collection hook — `mutate` resolves the onSave promise by invoking
// onSuccess with a fresh collection id.
const mockCreateMutate = vi.fn(
  (_data: unknown, opts?: { onSuccess?: (c: { id: string }) => void }) =>
    opts?.onSuccess?.({ id: "new-coll" }),
);
vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: mockCreateMutate }),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

function renderSarView() {
  return render(
    <SarView
      molecules={molecules}
      collectionId="col-1"
      projects={[{ id: "p1", name: "Project 1" }]}
      defaultProjectId="p1"
      sourceLabel="Test set"
    />,
    { wrapper },
  );
}

describe("SarView", () => {
  beforeEach(() => {
    mockMutate.mockClear();
    mockCreateMutate.mockClear();
    mockCustomInstance.mockClear();
    mockUseSarActivity.mockClear();
    mockUseSarActivity.mockReturnValue({ activityByMolecule: FIXED_ACTIVITY, isFetching: false });
    _decompositionData = DECOMPOSITION;
    _colorControlOnChange = null;
  });

  // ── Plan A tests (unchanged) ──────────────────────────────────────────────

  it("decomposes against the chosen core with the molecule ids", () => {
    renderSarView();
    // No core yet → no decomposition fired on mount.
    expect(mockMutate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("set-core"));

    expect(mockMutate).toHaveBeenCalledWith({
      moleculeIds: ["m1", "m2"],
      coreSmiles: "c1ccccc1",
    });
  });

  it("renders the table when a decomposition result is present", () => {
    renderSarView();
    expect(screen.getByTestId("rgroup-table")).toBeInTheDocument();
  });

  it("opens the save dialog when a table selection is saved", () => {
    renderSarView();
    // Dialog closed → its stub renders nothing.
    expect(screen.queryByTestId("confirm-save")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("save-selection"));

    // Dialog open → the stub now renders its confirm trigger.
    expect(screen.getByTestId("confirm-save")).toBeInTheDocument();
  });

  it("creates the collection then bulk-adds the selected molecules on save", async () => {
    renderSarView();
    // Open the dialog via the table-stub save trigger.
    fireEvent.click(screen.getByTestId("save-selection"));
    // Confirm the save → fires onSave (create → bulk-add).
    fireEvent.click(await screen.findByTestId("confirm-save"));

    await waitFor(() => {
      expect(mockCreateMutate).toHaveBeenCalledWith(
        { name: "Series A", project_id: null },
        expect.anything(),
      );
    });

    await waitFor(() => {
      expect(mockCustomInstance).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/collections/new-coll/molecules",
          method: "POST",
          data: { references: [{ value: "m1", ref_type: "uuid" }] },
        }),
      );
    });
  });

  // ── B5 tests ──────────────────────────────────────────────────────────────

  it("renders the color control", () => {
    renderSarView();
    expect(screen.getByTestId("rgroup-color-control")).toBeInTheDocument();
  });

  it("calls useSarActivity with null colorSpec on initial render", () => {
    renderSarView();
    expect(mockUseSarActivity).toHaveBeenCalledWith(expect.objectContaining({ colorSpec: null }));
  });

  it("calls useSarActivity with the colorSpec once the control fires onChange", () => {
    renderSarView();
    fireEvent.click(screen.getByTestId("set-color-spec"));
    expect(mockUseSarActivity).toHaveBeenCalledWith(
      expect.objectContaining({ colorSpec: FIXED_COLOR_SPEC }),
    );
  });

  it("shows the Table/Heatmap sub-toggle only when a decomposition result exists", () => {
    // Make decompose return no data.
    _decompositionData = undefined;
    renderSarView();
    expect(screen.queryByRole("button", { name: "Table view" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Heatmap view" })).not.toBeInTheDocument();
  });

  it("shows the sub-toggle when a result exists", () => {
    renderSarView();
    expect(screen.getByRole("button", { name: "Table view" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Heatmap view" })).toBeInTheDocument();
  });

  it("heatmap button is disabled when no colorSpec is set (single R-group result)", () => {
    // DECOMPOSITION_ONE_GROUP is the default — rgroup_labels.length < 2 AND no colorSpec.
    renderSarView();
    const heatmapBtn = screen.getByRole("button", { name: "Heatmap view" });
    expect(heatmapBtn).toBeDisabled();
  });

  it("heatmap button is disabled when colorSpec is set but <2 R-positions", () => {
    renderSarView();
    // Set a colorSpec via the control stub.
    fireEvent.click(screen.getByTestId("set-color-spec"));
    // Still 1 R-group → disabled.
    const heatmapBtn = screen.getByRole("button", { name: "Heatmap view" });
    expect(heatmapBtn).toBeDisabled();
  });

  it("heatmap button is disabled when ≥2 R-positions but no colorSpec", () => {
    _decompositionData = DECOMPOSITION_TWO_GROUPS;
    renderSarView();
    // colorSpec is null by default → disabled.
    const heatmapBtn = screen.getByRole("button", { name: "Heatmap view" });
    expect(heatmapBtn).toBeDisabled();
  });

  it("heatmap button is enabled when ≥2 R-positions AND colorSpec is set", () => {
    _decompositionData = DECOMPOSITION_TWO_GROUPS;
    renderSarView();
    fireEvent.click(screen.getByTestId("set-color-spec"));
    const heatmapBtn = screen.getByRole("button", { name: "Heatmap view" });
    expect(heatmapBtn).not.toBeDisabled();
  });

  it("clicking Heatmap switches the render from table to heatmap", () => {
    _decompositionData = DECOMPOSITION_TWO_GROUPS;
    renderSarView();
    // Enable heatmap by setting colorSpec first.
    fireEvent.click(screen.getByTestId("set-color-spec"));
    expect(screen.getByTestId("rgroup-table")).toBeInTheDocument();
    expect(screen.queryByTestId("rgroup-heatmap")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Heatmap view" }));

    expect(screen.queryByTestId("rgroup-table")).not.toBeInTheDocument();
    expect(screen.getByTestId("rgroup-heatmap")).toBeInTheDocument();
  });

  it("clicking Table switches back from heatmap to table", () => {
    _decompositionData = DECOMPOSITION_TWO_GROUPS;
    renderSarView();
    fireEvent.click(screen.getByTestId("set-color-spec"));
    fireEvent.click(screen.getByRole("button", { name: "Heatmap view" }));
    expect(screen.getByTestId("rgroup-heatmap")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Table view" }));

    expect(screen.getByTestId("rgroup-table")).toBeInTheDocument();
    expect(screen.queryByTestId("rgroup-heatmap")).not.toBeInTheDocument();
  });

  it("falls back to table when colorSpec is cleared while in heatmap mode", () => {
    _decompositionData = DECOMPOSITION_TWO_GROUPS;
    renderSarView();
    fireEvent.click(screen.getByTestId("set-color-spec"));
    fireEvent.click(screen.getByRole("button", { name: "Heatmap view" }));
    expect(screen.getByTestId("rgroup-heatmap")).toBeInTheDocument();

    // Clear the color spec → heatmap guard fails → table shown.
    fireEvent.click(screen.getByTestId("clear-color-spec"));

    expect(screen.getByTestId("rgroup-table")).toBeInTheDocument();
    expect(screen.queryByTestId("rgroup-heatmap")).not.toBeInTheDocument();
  });
});
