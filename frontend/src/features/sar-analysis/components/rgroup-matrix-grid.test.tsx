import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RGroupMatrixGrid } from "./rgroup-matrix-grid";

vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));

describe("RGroupMatrixGrid axis labels", () => {
  it("draws an unnamed substituent without its SMILES as text, keeping the SMILES on hover", () => {
    const unnamed = "CCCCCCc1ccc(O[*:1])c(O)c1";
    render(
      <RGroupMatrixGrid
        yLabel="R1"
        xLabel="R2"
        yValues={[unnamed, "Cl[*:1]"]}
        xValues={["[H][*:2]"]}
        cells={new Map()}
        onCellClick={() => {}}
      />,
    );
    expect(screen.queryByText("CCCCCCc1ccc(O*)c(O)c1")).toBeNull();
    expect(screen.getByTitle(unnamed)).toBeInTheDocument();
    // Named fragments and –H keep their short text.
    expect(screen.getByText("Cl")).toBeInTheDocument();
    expect(screen.getByText("–H")).toBeInTheDocument();
  });
});
