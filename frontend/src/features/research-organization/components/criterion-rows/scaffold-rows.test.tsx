import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ScaffoldCriterion } from "../../types";
import { ScaffoldCriterionRow } from "./scaffold-rows";

// Stub the chemistry components so jsdom doesn't try to load RDKit.js WASM
// or mount Ketcher. We assert on the surface contract (presence + props).
vi.mock("@/shared/components/chemistry", () => ({
  StructureRenderer: ({ smiles }: { smiles: string }) => (
    <div data-testid="structure-preview">{smiles}</div>
  ),
  StructureEditorDialog: ({
    open,
    onApply,
  }: {
    open: boolean;
    onApply: (s: string, f: "smiles" | "smarts") => void;
  }) =>
    open ? (
      <div data-testid="ketcher-dialog">
        <button
          type="button"
          data-testid="ketcher-apply-stub"
          onClick={() => onApply("c1ccncc1", "smiles")}
        >
          apply
        </button>
      </div>
    ) : null,
}));

const baseExact: ScaffoldCriterion = {
  type: "scaffold",
  mode: "exact_match",
  scaffold_smiles: "",
};

describe("ScaffoldCriterionRow", () => {
  it("renders mode picker + SMILES input in exact_match mode", () => {
    render(<ScaffoldCriterionRow criterion={baseExact} onChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByPlaceholderText(/scaffold smiles/i)).toBeInTheDocument();
  });

  it("hides the SMILES input in acyclic_only mode", () => {
    render(
      <ScaffoldCriterionRow
        criterion={{ type: "scaffold", mode: "acyclic_only" }}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.queryByPlaceholderText(/scaffold smiles/i)).not.toBeInTheDocument();
  });

  it("emits onChange with the typed SMILES", () => {
    const onChange = vi.fn();
    render(<ScaffoldCriterionRow criterion={baseExact} onChange={onChange} onRemove={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText(/scaffold smiles/i), {
      target: { value: "c1ccncc1" },
    });
    expect(onChange).toHaveBeenLastCalledWith({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });

  it("emits onChange when mode switches to acyclic_only (drops smiles)", () => {
    const onChange = vi.fn();
    render(
      <ScaffoldCriterionRow
        criterion={{ ...baseExact, scaffold_smiles: "c1ccncc1" }}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /acyclic/i }));
    expect(onChange).toHaveBeenLastCalledWith({
      type: "scaffold",
      mode: "acyclic_only",
    });
  });

  it("calls onRemove when the trash icon is clicked", () => {
    const onRemove = vi.fn();
    render(<ScaffoldCriterionRow criterion={baseExact} onChange={vi.fn()} onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: /remove criterion/i }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("shows a Draw button in exact_match mode (Edit when a SMILES is present)", () => {
    const { rerender } = render(
      <ScaffoldCriterionRow criterion={baseExact} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /^draw$/i })).toBeInTheDocument();

    rerender(
      <ScaffoldCriterionRow
        criterion={{ ...baseExact, scaffold_smiles: "c1ccncc1" }}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
  });

  it("renders the structure preview when scaffold_smiles is non-empty", () => {
    const { rerender } = render(
      <ScaffoldCriterionRow criterion={baseExact} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.queryByTestId("structure-preview")).toBeNull();

    rerender(
      <ScaffoldCriterionRow
        criterion={{ ...baseExact, scaffold_smiles: "c1ccncc1" }}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    const preview = screen.getByTestId("structure-preview");
    expect(preview).toHaveTextContent("c1ccncc1");
  });

  it("opens the editor on Draw click and applies the drawn structure", () => {
    const onChange = vi.fn();
    render(<ScaffoldCriterionRow criterion={baseExact} onChange={onChange} onRemove={vi.fn()} />);
    // Dialog hidden initially
    expect(screen.queryByTestId("ketcher-dialog")).toBeNull();
    // Click Draw → stub dialog mounts
    fireEvent.click(screen.getByRole("button", { name: /^draw$/i }));
    expect(screen.getByTestId("ketcher-dialog")).toBeInTheDocument();
    // Stub's apply fires onApply with "c1ccncc1" → row updates state
    fireEvent.click(screen.getByTestId("ketcher-apply-stub"));
    expect(onChange).toHaveBeenLastCalledWith({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });

  it("hides the Draw button and preview in acyclic_only mode", () => {
    render(
      <ScaffoldCriterionRow
        criterion={{ type: "scaffold", mode: "acyclic_only" }}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /^draw$/i })).toBeNull();
    expect(screen.queryByTestId("structure-preview")).toBeNull();
  });
});
