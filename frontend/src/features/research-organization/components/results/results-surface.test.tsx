import { describe, expect, it, vi, beforeAll } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ResultsSurface } from "./results-surface";
import type { Molecule } from "@/features/chemical-registration/types";

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
    expect(screen.getByRole("button", { name: /card view/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByTestId("mol-thumb")).toHaveLength(2);
  });

  it("renders the table toggle in pressed state when mode=table", () => {
    render(
      <ResultsSurface
        molecules={mols}
        mode="table"
        onModeChange={vi.fn()}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    // Assert that the ViewModeToggle reflects table mode correctly.
    // AG Grid may not render cells in jsdom (it relies on layout that jsdom lacks),
    // so we only assert on the toggle's aria-pressed state here.
    expect(screen.getByRole("button", { name: /table view/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("calls onModeChange when the inactive toggle is clicked", () => {
    const onModeChange = vi.fn();
    render(
      <ResultsSurface
        molecules={mols}
        mode="cards"
        onModeChange={onModeChange}
        selectedIds={new Set()}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    expect(onModeChange).toHaveBeenCalledWith("table");
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
    expect(screen.queryByRole("button", { name: /card view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /table view/i })).not.toBeInTheDocument();
  });
});
