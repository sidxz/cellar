import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SarView } from "./sar-view";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const DECOMPOSITION: RGroupDecompositionResponse = {
  core_smiles: "c1ccccc1",
  rgroup_labels: ["R1"],
  assignments: [{ molecule_id: "m1", rgroups: { R1: "C" } }],
  unmatched_ids: ["m2"],
};

const molecules = [
  { id: "m1", structure: { smiles: "Cc1ccccc1" } } as never,
  { id: "m2", structure: { smiles: "Clc1ccccc1" } } as never,
];

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Decomposition hook — `.mutate` is a spy, `.data` is the fixed fixture.
const mockMutate = vi.fn();
vi.mock("../hooks/use-rgroup-decomposition", () => ({
  useRGroupDecomposition: () => ({
    mutate: mockMutate,
    data: DECOMPOSITION,
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
  });

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
});
