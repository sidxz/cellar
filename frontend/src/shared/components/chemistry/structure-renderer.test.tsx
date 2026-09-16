import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

const svgSpy = vi.fn((_opts: string) => "<svg/>");
vi.mock("@/shared/lib/rdkit/rdkit-loader", () => ({
  getRDKit: async () => ({
    get_mol: () => ({
      is_valid: () => true,
      get_svg: vi.fn(() => "<svg/>"),
      get_svg_with_highlights: svgSpy,
      get_substruct_match: () => JSON.stringify({ atoms: [0, 1], bonds: [0] }),
      delete: () => {},
    }),
    get_qmol: () => ({ is_valid: () => true, delete: () => {} }),
  }),
}));

import { StructureRenderer } from "./structure-renderer";

beforeAll(() => {
  // jsdom has no blob URLs.
  globalThis.URL.createObjectURL = vi.fn(() => "blob:structure");
  globalThis.URL.revokeObjectURL = vi.fn();
});

describe("StructureRenderer draws on a transparent background", () => {
  it("passes clearBackground=false together with the size", async () => {
    render(<StructureRenderer smiles="CCO" width={120} height={80} />);
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument());
    const opts = JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}");
    expect(opts).toMatchObject({ width: 120, height: 80, clearBackground: false });
  });

  it("keeps the highlight atoms/bonds alongside the background option", async () => {
    render(<StructureRenderer smiles="CCO" highlightSmarts="C" />);
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument());
    const opts = JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}");
    expect(opts).toMatchObject({ clearBackground: false, atoms: [0, 1], bonds: [0] });
  });
});
