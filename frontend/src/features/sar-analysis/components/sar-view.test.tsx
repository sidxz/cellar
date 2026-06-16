import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SarView } from "./sar-view";

// ---------------------------------------------------------------------------
// Controllable hook returns (mutated per test before render)
// ---------------------------------------------------------------------------
type RunReturn = {
  runId: string | null;
  labels: string[];
  counts: { matched: number; unmatched: number; total: number } | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};
type ProjReturn = {
  projectionId: string | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};

const READY_RUN: RunReturn = {
  runId: "run-1",
  labels: ["R1", "R2"],
  counts: { matched: 8, unmatched: 2, total: 10 },
  status: "ready",
  isStarting: false,
  isPolling: false,
  error: null,
};
const READY_PROJ: ProjReturn = {
  projectionId: "proj-1",
  status: "ready",
  isStarting: false,
  isPolling: false,
  error: null,
};

let runReturn: RunReturn = { ...READY_RUN };
let projReturn: ProjReturn = { ...READY_PROJ };

vi.mock("../hooks/use-decomposition-run", () => ({
  useDecompositionRun: () => runReturn,
}));
vi.mock("../hooks/use-activity-projection", () => ({
  useActivityProjection: () => projReturn,
  channelFromColorSpec: () => ({ column: "drc:rd1", selection_rule: "latest_approved_run" }),
}));

vi.mock("../lib/sar-handoff", () => ({ readSarHandoff: () => null }));

const mockSaveAll = vi.fn().mockResolvedValue({ collection_id: "all-coll" });
vi.mock("../hooks/use-save-decomposition-collection", () => ({
  useSaveDecompositionCollection: () => ({ saveAll: mockSaveAll }),
}));

const mockCustomInstance = vi.fn().mockResolvedValue({});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: unknown[]) => mockCustomInstance(...args),
}));

const mockCreateMutate = vi.fn(
  (_data: unknown, opts?: { onSuccess?: (c: { id: string }) => void }) =>
    opts?.onSuccess?.({ id: "new-coll" }),
);
vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: mockCreateMutate }),
}));

vi.mock("./rgroup-core-picker", () => ({
  RGroupCorePicker: () => <div data-testid="rgroup-core-picker">core picker</div>,
}));

vi.mock("./rgroup-color-control", () => ({
  RGroupColorControl: ({ onChange }: { onChange: (spec: unknown) => void }) => (
    <div data-testid="rgroup-color-control">
      <button
        type="button"
        data-testid="set-color-spec"
        onClick={() =>
          onChange({
            protocolId: "p1",
            column: "drc:rd1",
            interceptKey: null,
            source: "dr_curve",
            label: "EGFR · IC50",
          })
        }
      >
        set color
      </button>
      <button type="button" data-testid="clear-color-spec" onClick={() => onChange(null)}>
        clear color
      </button>
    </div>
  ),
}));

vi.mock("./rgroup-table", () => ({
  RGroupTable: ({
    onSaveSelection,
    onSaveAll,
  }: {
    onSaveSelection: (rows: { id: string; label: string }[]) => void;
    onSaveAll?: (a: {
      count: number;
      filter?: Record<string, unknown>;
      projectionId?: string | null;
    }) => void;
  }) => (
    <div data-testid="rgroup-table">
      <button
        type="button"
        data-testid="save-selection"
        onClick={() => onSaveSelection([{ id: "m1", label: "CV-1" }])}
      >
        save
      </button>
      <button
        type="button"
        data-testid="save-all"
        onClick={() =>
          onSaveAll?.({
            count: 8,
            filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
            projectionId: "proj-1",
          })
        }
      >
        save all
      </button>
    </div>
  ),
}));

vi.mock("./rgroup-heatmap", () => ({
  RGroupHeatmap: () => <div data-testid="rgroup-heatmap">heatmap</div>,
}));

vi.mock("./save-selection-dialog", () => ({
  SaveSelectionDialog: ({
    open,
    onSave,
  }: {
    open: boolean;
    onSave: (a: { name: string; projectId: string | null }) => Promise<void>;
  }) =>
    open ? (
      <button
        type="button"
        data-testid="confirm-save"
        onClick={() => onSave({ name: "Series A", projectId: null })}
      >
        confirm save
      </button>
    ) : null,
}));

const molecules = [
  { id: "m1", structure: { smiles: "Cc1ccccc1" } } as never,
  { id: "m2", structure: { smiles: "Clc1ccccc1" } } as never,
];

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

describe("SarView (server orchestration)", () => {
  beforeEach(() => {
    mockSaveAll.mockClear();
    mockCreateMutate.mockClear();
    mockCustomInstance.mockClear();
    runReturn = { ...READY_RUN };
    projReturn = { ...READY_PROJ };
  });

  it("renders the color control + core picker", () => {
    renderSarView();
    expect(screen.getByTestId("rgroup-color-control")).toBeInTheDocument();
    expect(screen.getByTestId("rgroup-core-picker")).toBeInTheDocument();
  });

  it("shows the Table/Heatmap sub-toggle once the run is ready", () => {
    renderSarView();
    expect(screen.getByRole("button", { name: "Table view" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Heatmap view" })).toBeInTheDocument();
    expect(screen.getByTestId("rgroup-table")).toBeInTheDocument();
  });

  it("hides the sub-toggle while the run is still pending", () => {
    runReturn = {
      ...READY_RUN,
      runId: null,
      status: "pending",
      isPolling: true,
      labels: [],
      counts: null,
    };
    renderSarView();
    expect(screen.queryByRole("button", { name: "Heatmap view" })).not.toBeInTheDocument();
    expect(screen.getByText("Decomposing…")).toBeInTheDocument();
  });

  it("disables the heatmap toggle until a colorSpec + ready projection exist", () => {
    renderSarView();
    // run ready w/ 2 labels, but no colorSpec picked yet → disabled.
    expect(screen.getByRole("button", { name: "Heatmap view" })).toBeDisabled();
  });

  it("enables the heatmap toggle with ≥2 labels + colorSpec + ready projection, and switches", () => {
    renderSarView();
    fireEvent.click(screen.getByTestId("set-color-spec"));
    const heatmapBtn = screen.getByRole("button", { name: "Heatmap view" });
    expect(heatmapBtn).not.toBeDisabled();
    fireEvent.click(heatmapBtn);
    expect(screen.getByTestId("rgroup-heatmap")).toBeInTheDocument();
    expect(screen.queryByTestId("rgroup-table")).not.toBeInTheDocument();
  });

  it("creates the collection then bulk-adds the selected molecules on save", async () => {
    renderSarView();
    fireEvent.click(screen.getByTestId("save-selection"));
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

  it("saves all matched via the server endpoint with the live filter + projection", async () => {
    renderSarView();
    fireEvent.click(screen.getByTestId("save-all"));
    fireEvent.click(await screen.findByTestId("confirm-save"));
    await waitFor(() =>
      expect(mockSaveAll).toHaveBeenCalledWith({
        runId: "run-1",
        name: "Series A",
        projectId: null,
        filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
        projectionId: "proj-1",
      }),
    );
  });
});
