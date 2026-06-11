import { describe, expect, it } from "vitest";
import { fragmentDisplay } from "./sar-fragment-label";

// Fragment SMILES below are the EXACT canonical forms RDKit's RGroupDecompose
// (asSmiles=True) emits — verified against the backend RDKit. The attachment
// dummy is written last (e.g. `N#C[*:1]`), and the atom-map index is the
// R-group number (`:1`, `:2`, …).

describe("fragmentDisplay — known substituents", () => {
  it("maps common substituents to compact human labels", () => {
    expect(fragmentDisplay("F[*:1]").label).toBe("F");
    expect(fragmentDisplay("Cl[*:1]").label).toBe("Cl");
    expect(fragmentDisplay("C[*:1]").label).toBe("Me");
    expect(fragmentDisplay("CO[*:1]").label).toBe("OMe");
    expect(fragmentDisplay("O[*:1]").label).toBe("OH");
    expect(fragmentDisplay("N[*:1]").label).toBe("NH₂");
    expect(fragmentDisplay("N#C[*:1]").label).toBe("CN");
    expect(fragmentDisplay("FC(F)(F)[*:1]").label).toBe("CF₃");
    expect(fragmentDisplay("NC(=O)[*:1]").label).toBe("CONH₂");
    expect(fragmentDisplay("O=C(O)[*:1]").label).toBe("CO₂H");
    expect(fragmentDisplay("O=[N+]([O-])[*:1]").label).toBe("NO₂");
    expect(fragmentDisplay("c1ccc([*:1])cc1").label).toBe("Ph");
  });

  it("carries the full chemical name in the hover title", () => {
    expect(fragmentDisplay("N#C[*:1]").title.toLowerCase()).toContain("nitrile");
    expect(fragmentDisplay("NC(=O)[*:1]").title.toLowerCase()).toContain("carboxamide");
  });

  it("keeps the raw fragment SMILES as the thumbnail source for non-hydrogen", () => {
    expect(fragmentDisplay("N#C[*:1]").thumbnailSmiles).toBe("N#C[*:1]");
    expect(fragmentDisplay("N#C[*:1]").isHydrogen).toBe(false);
  });
});

describe("fragmentDisplay — hydrogen (unsubstituted)", () => {
  it("flags hydrogen and renders a plain –H label without a thumbnail", () => {
    const h = fragmentDisplay("[H][*:1]");
    expect(h.isHydrogen).toBe(true);
    expect(h.label).toBe("–H");
    expect(h.thumbnailSmiles).toBeNull();
    expect(h.title.toLowerCase()).toContain("unsubstituted");
  });
});

describe("fragmentDisplay — atom-map index is collapsed (R1 vs R2 etc.)", () => {
  it("gives the same result regardless of the R-group index", () => {
    expect(fragmentDisplay("F[*:2]").label).toBe("F");
    expect(fragmentDisplay("N#C[*:3]").label).toBe("CN");
    expect(fragmentDisplay("[H][*:2]").isHydrogen).toBe(true);
  });
});

describe("fragmentDisplay — unknown fragments never get an invented name", () => {
  it("falls back to a cleaned SMILES (attachment as *), never exposing [*:n]", () => {
    const d = fragmentDisplay("Cc1ccc(Cl)cc1[*:1]");
    expect(d.isHydrogen).toBe(false);
    expect(d.label).not.toMatch(/\[\*/); // no raw attachment SMARTS in the label
    expect(d.label).toBe("Cc1ccc(Cl)cc1*");
    // the exact raw SMILES stays recoverable on hover + drives the thumbnail
    expect(d.thumbnailSmiles).toBe("Cc1ccc(Cl)cc1[*:1]");
    expect(d.title).toContain("Cc1ccc(Cl)cc1[*:1]");
  });

  it("handles an empty / missing fragment without throwing", () => {
    expect(fragmentDisplay("").label).toBe("—");
    expect(fragmentDisplay("").thumbnailSmiles).toBeNull();
  });
});
