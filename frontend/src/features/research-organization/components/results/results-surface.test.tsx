import type { Molecule } from "@/features/chemical-registration/types";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ResultsSurface } from "./results-surface";

vi.mock("@/shared/components/molecule-thumbnail", () => ({
  MoleculeThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="mol-thumb" data-smiles={smiles} />
  ),
}));

vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="struct-thumb" data-smiles={smiles} />
  ),
}));

vi.mock("@/features/sar-analysis/components/scaffold-tree-view", () => ({
  ScaffoldTreeView: () => <div data-testid="scaffold-tree-view" />,
}));

vi.mock("@/features/sar-analysis/components/cluster-map-view", () => ({
  ClusterMapView: () => <div data-testid="cluster-map-view" />,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("../../hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));

// jsdom doesn't implement ResizeObserver. Stub it so react-virtual's measure
// path can run without throwing.
beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

function mol(id: string, name: string, smiles: string): Molecule {
  return {
    id,
    name,
    registration_number: `CV-${id}`,
    structure: { smiles, cxsmiles: null, inchi: null, inchi_key: null },
    descriptors: {
      molecular_weight: null,
      logp: null,
      ro5_violations: null,
      molecular_formula: null,
      exact_mass: null,
      tpsa: null,
      hbd: null,
      hba: null,
      rotatable_bonds: null,
      aromatic_rings: null,
      ring_count: null,
      heavy_atom_count: null,
    },
  } as Molecule;
}

const mols = [mol("1", "Mol One", "CCO"), mol("2", "Mol Two", "CCC")];

describe("ResultsSurface", () => {
  it("renders ViewModeToggle and the card grid when mode=cards", () => {
    render(
      <ResultsSurface
        molecules={mols}
        mode="cards"
        onModeChange={vi.fn()}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /grid view/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getAllByTestId("mol-thumb")).toHaveLength(2);
  });

  it("does not render the view-mode toggle when showToolbar is false", () => {
    render(
      <ResultsSurface
        molecules={mols}
        mode="cards"
        onModeChange={vi.fn()}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
        showToolbar={false}
      />,
    );
    expect(screen.queryByRole("button", { name: /grid view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /list view/i })).not.toBeInTheDocument();
  });

  it("renders ScaffoldTreeView when mode=scaffold-tree", () => {
    render(
      <ResultsSurface
        molecules={mols}
        mode="scaffold-tree"
        onModeChange={vi.fn()}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByTestId("scaffold-tree-view")).toBeInTheDocument();
    // Toggle should reflect scaffold-tree as active
    expect(screen.getByRole("button", { name: /scaffold view/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("renders ClusterMapView when mode=clusters", () => {
    render(
      <ResultsSurface
        molecules={mols}
        mode="clusters"
        onModeChange={vi.fn()}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByTestId("cluster-map-view")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cluster view/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("disables cluster toggle when molecule count < 10", () => {
    render(
      <ResultsSurface
        molecules={mols}
        mode="cards"
        onModeChange={vi.fn()}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    // mols has 2 entries, so cluster should be disabled
    expect(screen.getByRole("button", { name: /cluster view/i })).toBeDisabled();
  });
});
