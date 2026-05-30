import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/shared/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: any) => (
    <div data-testid="panel-group">{children}</div>
  ),
  ResizablePanel: ({ children }: any) => <div data-testid="panel">{children}</div>,
  ResizableHandle: () => <div data-testid="resize-handle" />,
}));

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => <div data-testid="plotly" /> }));

// Stub ClusterScatter: clicking it simulates a lasso of {a, b}.
vi.mock("./cluster-scatter", () => ({
  ClusterScatter: ({ onSelected }: any) => (
    <div data-testid="cluster-scatter" onClick={() => onSelected(["a", "b"])} />
  ),
}));

// Basket pane reads `basketIds`.
vi.mock("./cluster-selection-pane", () => ({
  ClusterSelectionPane: ({ basketIds }: any) => (
    <div data-testid="selection-pane">basket:{basketIds.size}</div>
  ),
}));

vi.mock("./save-selection-dialog", () => ({
  SaveSelectionDialog: ({ open, onClose }: any) =>
    open ? (
      <div data-testid="save-dialog">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

// Fixed UMAP result (representatives = [a]).
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

// Region pick hook — idle by default.
vi.mock("@/features/sar-analysis/hooks/use-region-diverse-pick", () => ({
  useRegionDiversePick: vi.fn(() => ({
    pickedIds: new Set<string>(),
    loading: false,
    error: null,
    active: false,
    pick: vi.fn(),
    reset: vi.fn(),
  })),
}));

import { ClusterMapView } from "./cluster-map-view";

const molecules: any[] = Array.from({ length: 10 }, (_, i) => ({
  id: String.fromCharCode(97 + i),
  name: `Mol ${i}`,
  bemis_murcko_smiles: "",
  structure: { smiles: "CCC" },
}));

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

describe("ClusterMapView", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders the scatter, basket pane, and split group", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(screen.getByTestId("cluster-scatter")).toBeInTheDocument();
    expect(screen.getByTestId("selection-pane")).toBeInTheDocument();
    expect(screen.getByTestId("panel-group")).toBeInTheDocument();
    expect(screen.getByTestId("resize-handle")).toBeInTheDocument();
  });

  it("renders the Diversify button and an empty basket bar", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(
      screen.getByRole("button", { name: /diversify/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/basket: 0/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save as collection/i }),
    ).toBeDisabled();
  });

  it("lasso → Add all adds the region to the basket and enables Save", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    fireEvent.click(screen.getByTestId("cluster-scatter"));
    expect(screen.getByText(/2 in region/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add all \(2\)/i }));
    expect(screen.getByText(/basket: 2/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save as collection/i }),
    ).not.toBeDisabled();
  });

  it("opens the SaveSelectionDialog from the basket bar once non-empty", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    fireEvent.click(screen.getByTestId("cluster-scatter"));
    fireEvent.click(screen.getByRole("button", { name: /add all \(2\)/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /save as collection/i }),
    );
    expect(screen.getByTestId("save-dialog")).toBeInTheDocument();
  });

  it("Add Diversify picks seeds the basket from representatives", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    fireEvent.click(
      screen.getByRole("button", { name: /add diversify picks \(1\)/i }),
    );
    expect(screen.getByText(/basket: 1/i)).toBeInTheDocument();
  });

  it("passes collectionId only when on a collection page (XOR moleculeIds)", async () => {
    const { useUmapCluster } = await import(
      "@/features/sar-analysis/hooks/use-umap-cluster"
    );
    (useUmapCluster as any).mockClear();
    render(<ClusterMapView {...defaultProps} collectionId="col-1" />, {
      wrapper,
    });
    const call = (useUmapCluster as any).mock.calls[0][0];
    expect(call.collectionId).toBe("col-1");
    expect(call.moleculeIds).toBeUndefined();
  });

  it("shows a 'not enough molecules' message when fewer than 10 mols", () => {
    render(
      <ClusterMapView {...defaultProps} molecules={molecules.slice(0, 3)} />,
      { wrapper },
    );
    expect(screen.getByText(/need at least 10 molecules/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cluster-scatter")).not.toBeInTheDocument();
  });
});
