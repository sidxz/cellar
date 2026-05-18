import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScaffoldCriterionRow } from "./scaffold-rows";
import type { ScaffoldCriterion } from "../../types";

const baseExact: ScaffoldCriterion = {
  type: "scaffold",
  mode: "exact_match",
  scaffold_smiles: "",
};

describe("ScaffoldCriterionRow", () => {
  it("renders mode picker + SMILES input in exact_match mode", () => {
    render(
      <ScaffoldCriterionRow
        criterion={baseExact}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
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
    render(
      <ScaffoldCriterionRow
        criterion={baseExact}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
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
    render(
      <ScaffoldCriterionRow
        criterion={baseExact}
        onChange={vi.fn()}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /remove criterion/i }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
