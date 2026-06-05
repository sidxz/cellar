import type { Molecule } from "@/features/chemical-registration/types";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { CardGrid } from "./card-grid";

vi.mock("@/shared/components/molecule-thumbnail", () => ({
  MoleculeThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="mol-thumb" data-smiles={smiles} />
  ),
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

function mol(id: string, name: string): Molecule {
  return {
    id,
    name,
    registration_number: `CV-${id}`,
    structure: { smiles: "CCO", cxsmiles: null, inchi: null, inchi_key: null },
    descriptors: {
      molecular_weight: 100,
      logp: 1.0,
      ro5_violations: 0,
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

describe("CardGrid", () => {
  it("renders empty state when there are no molecules", () => {
    render(
      <CardGrid molecules={[]} selectedIds={new Set()} onSelectChange={vi.fn()} onOpen={vi.fn()} />,
    );
    expect(screen.getByText(/no molecules/i)).toBeInTheDocument();
  });

  it("renders a tile per molecule (small set)", () => {
    const mols = [mol("1", "Mol One"), mol("2", "Mol Two"), mol("3", "Mol Three")];
    render(
      <CardGrid
        molecules={mols}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("Mol One")).toBeInTheDocument();
    expect(screen.getByText("Mol Two")).toBeInTheDocument();
    expect(screen.getByText("Mol Three")).toBeInTheDocument();
  });

  it("renders loading skeleton when isLoading is true", () => {
    render(
      <CardGrid
        molecules={[]}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
        isLoading
      />,
    );
    expect(screen.getAllByTestId("card-skeleton").length).toBeGreaterThan(0);
  });

  it("reflects selected state on the appropriate tile", () => {
    const mols = [mol("1", "Mol One"), mol("2", "Mol Two")];
    render(
      <CardGrid
        molecules={mols}
        selectedIds={new Set(["1"])}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    // Both tiles render; checkboxes are present via MoleculeCard
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[0]).toBeChecked();
    expect(checkboxes[1]).not.toBeChecked();
  });
});
