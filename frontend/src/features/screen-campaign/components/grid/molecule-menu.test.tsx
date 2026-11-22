import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompoundIdentity, aliasesOf, moleculeShortcuts } from "./molecule-menu";

const molecule = {
  registration_number: "CC-061463",
  name: "Quinmide",
  structure: { smiles: "c1ccccc1" },
  identifiers: [
    { identifier: "CC-061463", identifier_type: "registration_number" },
    { identifier: "Quinmide", identifier_type: "name" },
    { identifier: "CHEMBL2098183", identifier_type: "chembl_id" },
    { identifier: "41134477", identifier_type: "cdd_molecule_id" },
    { identifier: "SSID-1", identifier_type: "supplier" },
    { identifier: "SSID-2", identifier_type: "supplier" },
    { identifier: "SSID-3", identifier_type: "supplier" },
  ],
} as unknown as Parameters<typeof aliasesOf>[0];

describe("aliasesOf", () => {
  it("drops the name and registration number and marks vault ids (CDD)", () => {
    expect(aliasesOf(molecule)).toEqual([
      "CHEMBL2098183",
      "41134477 (CDD)",
      "SSID-1",
      "SSID-2",
      "SSID-3",
    ]);
  });
});

describe("moleculeShortcuts", () => {
  const MOL = "0b1e7c1e-0000-4000-8000-000000000001";

  it("opens the compound, searches by id, then copies", () => {
    const [open, copies] = moleculeShortcuts(MOL, molecule);
    expect(open?.map((s) => ("href" in s ? s.href : null))).toEqual([
      `/compounds/${MOL}`,
      `/search?molecule_id=${MOL}&mode=similar`,
      `/search?molecule_id=${MOL}&mode=substructure`,
    ]);
    expect(copies?.map((s) => s.label)).toEqual(["Copy SMILES", "Copy ID", "Copy alias"]);
  });

  it("offers no structure search or SMILES without a structure", () => {
    const labels = moleculeShortcuts(MOL, { ...molecule, structure: null } as typeof molecule)
      .flat()
      .map((s) => s.label);
    expect(labels).toEqual(["Open compound", "Copy ID", "Copy alias"]);
  });
});

describe("CompoundIdentity", () => {
  it("shows three identifiers, expands the rest in place, and folds them back", () => {
    render(<CompoundIdentity moleculeId="m-1" molecule={molecule} />);
    expect(screen.getByRole("link", { name: "CC-061463" })).toHaveAttribute(
      "href",
      "/compounds/m-1",
    );
    expect(screen.queryByText("SSID-2")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "+2 more" }));
    expect(screen.getByText("SSID-3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.queryByText("SSID-3")).toBeNull();
  });
});
