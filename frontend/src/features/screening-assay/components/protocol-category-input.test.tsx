import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProtocolCategoryInput } from "./protocol-category-input";

const state = vi.hoisted(() => ({ categories: [] as { label: string }[] }));

vi.mock("@/features/workspace-config/hooks/use-protocol-categories", () => ({
  useProtocolCategories: () => ({ data: state.categories }),
}));
vi.mock("./vocabulary-autocomplete", () => ({
  VocabularyAutocomplete: () => <div>free text fallback</div>,
}));

describe("ProtocolCategoryInput", () => {
  it("offers the workspace categories", () => {
    state.categories = [{ label: "Cytotoxicity" }, { label: "Enzyme inhibition" }];
    render(<ProtocolCategoryInput value="Cytotoxicity" onChange={() => {}} />);
    expect(screen.getByRole("combobox")).toHaveTextContent("Cytotoxicity");
  });

  it("keeps an off-list value visible", () => {
    state.categories = [{ label: "Cytotoxicity" }];
    render(<ProtocolCategoryInput value="Enzyme Assay" onChange={() => {}} />);
    expect(screen.getByRole("combobox")).toHaveTextContent("Enzyme Assay");
  });

  it("falls back to free text when the workspace has no categories", () => {
    state.categories = [];
    render(<ProtocolCategoryInput value="" onChange={() => {}} />);
    expect(screen.getByText("free text fallback")).toBeInTheDocument();
  });
});
