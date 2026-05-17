import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MoleculeCard } from "./molecule-card";
import type { Molecule } from "@/features/chemical-registration/types";

// MoleculeThumbnail renders an <img> via RDKit.js WASM — stub it in tests.
vi.mock("@/shared/components/molecule-thumbnail", () => ({
  MoleculeThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="mol-thumb" data-smiles={smiles} />
  ),
}));

const baseMol: Molecule = {
  id: "mol-1",
  name: "Test Mol",
  registration_number: "CV-00001",
  workspace_id: "ws-1",
  molecule_type: "small_molecule",
  structure: { smiles: "CCO", cxsmiles: null, inchi: null, inchi_key: null },
  descriptors: {
    molecular_formula: null,
    molecular_weight: 412.3,
    exact_mass: null,
    logp: 3.21,
    tpsa: null,
    hbd: null,
    hba: null,
    rotatable_bonds: null,
    aromatic_rings: null,
    ring_count: null,
    heavy_atom_count: null,
    ro5_violations: 0,
  },
  molecular_formula: null,
  structure_status: "disclosed",
  registration_status: "approved",
  synthesis_status: "available",
  lifecycle_stage: "registered",
  stereochemistry: null,
  tags: [],
  invention_date: null,
  disclosed_at: null,
  merged_into_id: null,
  custom_fields: null,
  originating_org_id: "org-1",
  identifiers: [],
  version: 1,
};

describe("MoleculeCard", () => {
  it("renders the structure thumbnail with the molecule's SMILES", () => {
    render(<MoleculeCard molecule={baseMol} selected={false} onSelectChange={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByTestId("mol-thumb")).toHaveAttribute("data-smiles", "CCO");
  });

  it("renders the registration number and name", () => {
    render(<MoleculeCard molecule={baseMol} selected={false} onSelectChange={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByText(/CV-00001/)).toBeInTheDocument();
    expect(screen.getByText(/Test Mol/)).toBeInTheDocument();
  });

  it("renders MW + cLogP + Ro5 ✓ when descriptors are present", () => {
    render(<MoleculeCard molecule={baseMol} selected={false} onSelectChange={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByText(/MW 412/)).toBeInTheDocument();
    expect(screen.getByText(/cLogP 3\.2/)).toBeInTheDocument();
    expect(screen.getByText(/Ro5/)).toBeInTheDocument();
  });

  it("reflects selected state on the checkbox", () => {
    render(<MoleculeCard molecule={baseMol} selected={true} onSelectChange={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("calls onSelectChange when the checkbox is toggled", () => {
    const onSelectChange = vi.fn();
    render(<MoleculeCard molecule={baseMol} selected={false} onSelectChange={onSelectChange} onOpen={vi.fn()} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onSelectChange).toHaveBeenCalledWith("mol-1", true);
  });

  it("calls onOpen when the tile body is clicked", () => {
    const onOpen = vi.fn();
    render(<MoleculeCard molecule={baseMol} selected={false} onSelectChange={vi.fn()} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: /open Test Mol detail/i }));
    expect(onOpen).toHaveBeenCalledWith("mol-1");
  });

  it("renders 'Tested in N protocols' when protocolCount > 0", () => {
    render(
      <MoleculeCard
        molecule={baseMol}
        selected={false}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
        protocolCount={3}
      />,
    );
    expect(screen.getByText("Tested in 3 protocols")).toBeInTheDocument();
  });

  it("does not render protocol count line when protocolCount is 0 or undefined", () => {
    const { rerender } = render(
      <MoleculeCard molecule={baseMol} selected={false} onSelectChange={vi.fn()} onOpen={vi.fn()} />,
    );
    expect(screen.queryByText(/tested in/i)).not.toBeInTheDocument();

    rerender(
      <MoleculeCard
        molecule={baseMol}
        selected={false}
        onSelectChange={vi.fn()}
        onOpen={vi.fn()}
        protocolCount={0}
      />,
    );
    expect(screen.queryByText(/tested in/i)).not.toBeInTheDocument();
  });
});
