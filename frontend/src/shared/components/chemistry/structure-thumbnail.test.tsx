import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

const svgSpy = vi.fn((_opts: string) => "<svg/>");
vi.mock("@/shared/lib/rdkit/rdkit-loader", () => ({
  getRDKit: async () => ({
    get_mol: () => ({ is_valid: () => true, get_svg_with_highlights: svgSpy, delete: () => {} }),
  }),
}));

import { StructureThumbnail } from "./structure-thumbnail";

beforeAll(() => {
  globalThis.URL.createObjectURL = vi.fn(() => "blob:thumb");
  globalThis.URL.revokeObjectURL = vi.fn();
});

describe("StructureThumbnail draws on a transparent background", () => {
  it("passes clearBackground=false with the 2x render size", async () => {
    render(<StructureThumbnail smiles="CCO" size={40} />);
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument());
    const opts = JSON.parse(svgSpy.mock.calls.at(-1)?.[0] ?? "{}");
    expect(opts).toMatchObject({ width: 80, height: 80, clearBackground: false });
  });
});
