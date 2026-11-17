import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RGroupMatrixGrid } from "./rgroup-matrix-grid";

// The real thumbnail is an <img alt="Structure">.
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: () => <img alt="Structure" src="data:," />,
}));

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

  it("names every axis header by its fragment; the drawing is decorative", () => {
    render(
      <RGroupMatrixGrid
        yLabel="R1"
        xLabel="R2"
        yValues={["CCCCCCc1ccc(O[*:1])c(O)c1", "Cl[*:1]"]}
        xValues={["[H][*:2]", "CCN[*:2]"]}
        cells={new Map()}
        onCellClick={() => {}}
      />,
    );
    expect(screen.getByRole("rowheader", { name: "CCCCCCc1ccc(O*)c(O)c1" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Cl" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "–H" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "CCN*" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Structure" })).toBeNull();
  });
});
