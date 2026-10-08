import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ProtocolCategoryAdmin } from "./protocol-category-admin";

const seed = vi.fn();
const update = vi.fn();
const create = vi.fn();
const remove = vi.fn();
const state = vi.hoisted(() => ({
  categories: [
    {
      id: "c1",
      workspace_id: "w",
      label: "Cytotoxicity",
      name_pattern: "{cell_line} cytotoxicity",
      default_pattern: "{cell_line} cytotoxicity",
      version: 1,
    },
    {
      id: "c2",
      workspace_id: "w",
      label: "Solubility",
      name_pattern: "Solubility",
      default_pattern: "{discriminator?} solubility",
      version: 1,
    },
  ],
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/protocol-categories" }));
vi.mock("../hooks/use-protocol-categories", () => ({
  useProtocolCategories: () => ({ data: state.categories, isLoading: false }),
  useSeedDefaultProtocolCategories: () => ({ mutate: seed, isPending: false }),
  useUpdateProtocolCategory: () => ({ mutateAsync: update, isPending: false }),
  useCreateProtocolCategory: () => ({ mutateAsync: create, isPending: false }),
  useDeleteProtocolCategory: () => ({ mutate: remove, isPending: false }),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
});

describe("ProtocolCategoryAdmin", () => {
  beforeEach(() => {
    seed.mockReset();
    update.mockReset();
  });

  it("lists categories and marks custom patterns", () => {
    render(<ProtocolCategoryAdmin />);
    const row = screen.getByText("Solubility", { selector: "td" }).closest("tr") as HTMLElement;
    expect(within(row).getByText("custom")).toBeInTheDocument();
    const cyto = screen.getByText("Cytotoxicity").closest("tr") as HTMLElement;
    expect(within(cyto).queryByText("custom")).not.toBeInTheDocument();
  });

  it("adds the default categories", () => {
    render(<ProtocolCategoryAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /add default categories/i }));
    expect(seed).toHaveBeenCalled();
  });

  it("edits a pattern and can reset it to the default", async () => {
    render(<ProtocolCategoryAdmin />);
    const row = screen.getByText("Solubility", { selector: "td" }).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /edit/i }));
    fireEvent.click(screen.getByRole("button", { name: /reset to default/i }));
    expect((screen.getByLabelText("Name pattern") as HTMLInputElement).value).toBe(
      "{discriminator?} solubility",
    );
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(update).toHaveBeenCalledWith({
      label: "Solubility",
      name_pattern: "{discriminator?} solubility",
    });
  });
});
