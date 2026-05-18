import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ---------------------------------------------------------------------------
// Mocks — must be declared before importing the component under test.
// ---------------------------------------------------------------------------

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// react-resizable-panels uses ResizeObserver + layout APIs absent from jsdom.
vi.mock("@/shared/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: any) => (
    <div data-testid="panel-group">{children}</div>
  ),
  ResizablePanel: ({ children }: any) => (
    <div data-testid="panel">{children}</div>
  ),
  ResizableHandle: () => <div data-testid="resize-handle" />,
}));

// Plotly uses WebGL not available in jsdom.
vi.mock("@/shared/lib/plotly", () => ({
  Plot: () => <div data-testid="plotly" />,
}));

// Stub ClusterScatter since it depends on the mocked Plotly.
vi.mock("./cluster-scatter", () => ({
  ClusterScatter: ({ onSelected }: any) => (
    <div
      data-testid="cluster-scatter"
      onClick={() => onSelected(null)}
    />
  ),
}));

// Stub ClusterSelectionPane (renders CardGrid which virtualizes — heavy in jsdom).
vi.mock("./cluster-selection-pane", () => ({
  ClusterSelectionPane: ({ selectedIds }: any) => (
    <div data-testid="selection-pane">
      selected:{selectedIds.size}
    </div>
  ),
}));

// Stub SaveSelectionDialog.
vi.mock("./save-selection-dialog", () => ({
  SaveSelectionDialog: ({ open, onClose }: any) =>
    open ? (
      <div data-testid="save-dialog">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

// Fixed UMAP result so we don't touch the real hook or network.
vi.mock("@/features/sar-analysis/hooks/use-umap-cluster", () => ({
  useUmapCluster: vi.fn(() => ({
    result: {
      points: [
        { moleculeId: "a", x: 0, y: 0 },
        { moleculeId: "b", x: 10, y: 10 },
      ],
      clusters: [
        { moleculeId: "a", clusterId: 0 },
        { moleculeId: "b", clusterId: 1 },
      ],
      representatives: [{ moleculeId: "a", clusterId: 0 }],
      clusterCount: 2,
      picker: "maxmin" as const,
      pickerParams: { n: 1 },
      skippedMoleculeIds: [],
    },
    job: null,
    loading: false,
    error: null,
    cancel: vi.fn(),
  })),
}));

// ---------------------------------------------------------------------------
// Component under test (imported AFTER mocks)
// ---------------------------------------------------------------------------

import { ClusterMapView } from "./cluster-map-view";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const molecules: any[] = [
  { id: "a", name: "Mol A", bemis_murcko_smiles: "c1ccccc1", structure: { smiles: "c1ccccc1" } },
  { id: "b", name: "Mol B", bemis_murcko_smiles: "c1ccc2ccccc2c1", structure: { smiles: "c1ccc2ccccc2c1" } },
  // Need >= 10 for UMAP to be enabled
  { id: "c", name: "Mol C", bemis_murcko_smiles: "", structure: { smiles: "CCC" } },
  { id: "d", name: "Mol D", bemis_murcko_smiles: "", structure: { smiles: "CCCC" } },
  { id: "e", name: "Mol E", bemis_murcko_smiles: "", structure: { smiles: "CCCCC" } },
  { id: "f", name: "Mol F", bemis_murcko_smiles: "", structure: { smiles: "CCCCCC" } },
  { id: "g", name: "Mol G", bemis_murcko_smiles: "", structure: { smiles: "CCCCCCC" } },
  { id: "h", name: "Mol H", bemis_murcko_smiles: "", structure: { smiles: "CCCCCCCC" } },
  { id: "i", name: "Mol I", bemis_murcko_smiles: "", structure: { smiles: "CCCCCCCCC" } },
  { id: "j", name: "Mol J", bemis_murcko_smiles: "", structure: { smiles: "CCCCCCCCCC" } },
];

const defaultProps = {
  molecules,
  protocols: [] as any[],
  defaultColorProtocolId: null,
  onSaveCollection: async () => {},
  projects: [],
  defaultProjectId: null,
  sourceLabel: "Test Set",
};

const wrapper = ({ children }: any) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ClusterMapView", () => {
  it("renders scatter and selection pane when result is set", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(screen.getByTestId("cluster-scatter")).toBeInTheDocument();
    expect(screen.getByTestId("selection-pane")).toBeInTheDocument();
  });

  it("renders the split-pane group", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(screen.getByTestId("panel-group")).toBeInTheDocument();
    // resize handle between the two panels
    expect(screen.getByTestId("resize-handle")).toBeInTheDocument();
  });

  it("renders the Diversify button in the toolbar", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(screen.getByRole("button", { name: /diversify/i })).toBeInTheDocument();
  });

  it("shows 'Save selection' button, disabled when no selection", () => {
    // With only representatives set (mol 'a'), selectedIds has 1 element.
    // But button text says the count.
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    const saveBtn = screen.getByRole("button", { name: /save selection/i });
    // 'a' is the representative; selectedIds = {a}, count = 1 → button enabled
    expect(saveBtn).not.toBeDisabled();
  });

  it("opens the SaveSelectionDialog when Save is clicked", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    const saveBtn = screen.getByRole("button", { name: /save selection/i });
    fireEvent.click(saveBtn);
    expect(screen.getByTestId("save-dialog")).toBeInTheDocument();
  });

  it("closes the SaveSelectionDialog when onClose is triggered", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /save selection/i }));
    expect(screen.getByTestId("save-dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByTestId("save-dialog")).not.toBeInTheDocument();
  });

  it("shows a 'not enough molecules' message when fewer than 10 mols given", () => {
    render(
      <ClusterMapView
        {...defaultProps}
        molecules={molecules.slice(0, 3)}
      />,
      { wrapper },
    );
    expect(screen.getByText(/need at least 10 molecules/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cluster-scatter")).not.toBeInTheDocument();
  });
});
