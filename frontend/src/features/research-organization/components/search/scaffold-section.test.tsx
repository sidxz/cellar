import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScaffoldSection } from "./scaffold-section";

// Stub chemistry components — see scaffold-rows.test.tsx for rationale.
vi.mock("@/shared/components/chemistry", () => ({
  StructureRenderer: () => null,
  StructureEditorDialog: () => null,
}));

describe("ScaffoldSection", () => {
  it("shows an empty-state message when no criteria are present", () => {
    render(<ScaffoldSection criteria={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/No scaffold filters/i)).toBeInTheDocument();
  });

  it("renders the Add button and emits a default criterion on click", () => {
    const onChange = vi.fn();
    render(<ScaffoldSection criteria={[]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual([
      { type: "scaffold", mode: "exact_match", scaffold_smiles: "" },
    ]);
  });

  it("renders a row per criterion and hides the empty state", () => {
    render(
      <ScaffoldSection
        criteria={[
          { type: "scaffold", mode: "acyclic_only" },
          { type: "scaffold", mode: "exact_match", scaffold_smiles: "c1ccncc1" },
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText(/No scaffold filters/i)).toBeNull();
    // The exact_match row exposes the SMILES input
    expect(screen.getByPlaceholderText(/Scaffold SMILES/i)).toBeInTheDocument();
  });

  it("removing a criterion emits the new array without it", () => {
    const onChange = vi.fn();
    render(
      <ScaffoldSection
        criteria={[
          { type: "scaffold", mode: "exact_match", scaffold_smiles: "c1ccncc1" },
        ]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /remove criterion/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("shows the Bemis-Murcko caption when any criterion is exact_match", () => {
    render(
      <ScaffoldSection
        criteria={[
          { type: "scaffold", mode: "exact_match", scaffold_smiles: "c1ccncc1" },
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/canonical Bemis-Murcko scaffold/i),
    ).toBeInTheDocument();
  });

  it("hides the caption when all rows are acyclic_only (or when empty)", () => {
    const { rerender } = render(
      <ScaffoldSection criteria={[]} onChange={vi.fn()} />,
    );
    expect(screen.queryByText(/canonical Bemis-Murcko/i)).toBeNull();

    rerender(
      <ScaffoldSection
        criteria={[{ type: "scaffold", mode: "acyclic_only" }]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText(/canonical Bemis-Murcko/i)).toBeNull();
  });
});
