import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const { svgSpy, matchSpy, queryDelete, molDelete, getMol, getQuery } = vi.hoisted(() => ({
  svgSpy: vi.fn((_opts: string) => "<svg/>"),
  matchSpy: vi.fn(() => JSON.stringify({ atoms: [0, 1], bonds: [0] })),
  queryDelete: vi.fn(),
  molDelete: vi.fn(),
  getMol: vi.fn(),
  getQuery: vi.fn(),
}));
vi.mock("@/shared/lib/rdkit/rdkit-loader", () => ({
  getRDKit: async () => ({
    get_mol: getMol,
    get_qmol: getQuery,
  }),
}));

import { StructureThumbnail } from "./structure-thumbnail";

beforeAll(() => {
  globalThis.URL.createObjectURL = vi.fn(() => "blob:thumb");
  globalThis.URL.revokeObjectURL = vi.fn();
});

beforeEach(() => {
  vi.clearAllMocks();
  getMol.mockImplementation(() => ({
    is_valid: () => true,
    get_svg_with_highlights: svgSpy,
    get_substruct_match: matchSpy,
    delete: molDelete,
  }));
  getQuery.mockImplementation(() => ({ is_valid: () => true, delete: queryDelete }));
  matchSpy.mockReturnValue(JSON.stringify({ atoms: [0, 1], bonds: [0] }));
});

describe("StructureThumbnail draws on a transparent background", () => {
  it("passes clearBackground=false with the 2x render size", async () => {
    render(<StructureThumbnail smiles="CCO" size={40} />);
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument());
    const opts = JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}");
    expect(opts).toMatchObject({ width: 80, height: 80, clearBackground: false });
    expect(screen.getByRole("img")).toHaveAttribute("height", "40");
  });

  it("draws into a box wider than tall when given a height", async () => {
    const { container } = render(<StructureThumbnail smiles="CCO" size={144} height={72} />);
    // The placeholder holds the same room while the drawing loads.
    expect(container.firstElementChild).toHaveStyle({ width: "144px", height: "72px" });
    const img = await screen.findByRole("img");
    const opts = JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}");
    expect(opts).toMatchObject({ width: 288, height: 144 });
    expect(img).toHaveAttribute("width", "144");
    expect(img).toHaveAttribute("height", "72");
  });
});

describe("query highlighting", () => {
  it("highlights the matched atoms/bonds and disposes the SMARTS query", async () => {
    render(<StructureThumbnail smiles="CCO" highlightQuery="[#6]-[#6]" queryKind="smarts" />);
    await screen.findByRole("img");
    expect(getQuery).toHaveBeenCalledWith("[#6]-[#6]");
    expect(JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}")).toMatchObject({
      atoms: [0, 1],
      bonds: [0],
    });
    expect(queryDelete).toHaveBeenCalledOnce();
    expect(molDelete).toHaveBeenCalledOnce();
  });
  it("parses a drawn SMILES query as a molecule for aromaticity perception", async () => {
    render(
      <StructureThumbnail smiles="c1ccccc1O" highlightQuery="C1=CC=CC=C1" queryKind="smiles" />,
    );
    await screen.findByRole("img");
    expect(getMol).toHaveBeenCalledWith("C1=CC=CC=C1");
    expect(getQuery).not.toHaveBeenCalled();
    expect(molDelete).toHaveBeenCalledTimes(2);
  });
  it("keeps the result structure visible when local highlighting is unsupported", async () => {
    matchSpy.mockImplementationOnce(() => {
      throw new Error("Unsupported query");
    });
    render(<StructureThumbnail smiles="CCO" highlightQuery="C" />);
    await screen.findByRole("img");
    expect(JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}")).not.toHaveProperty("atoms");
    expect(queryDelete).toHaveBeenCalledOnce();
    expect(molDelete).toHaveBeenCalledOnce();
  });
});
