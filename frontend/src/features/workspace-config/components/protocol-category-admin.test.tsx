import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    {
      id: "c3",
      workspace_id: "w",
      label: "Growth inhibition",
      name_pattern: "{organism} growth inhibition",
      default_pattern: "{organism} growth inhibition",
      version: 1,
    },
  ],
  // Only Growth inhibition has a form to copy; Cytotoxicity and Solubility have none.
  forms: [{ id: "f1", name: "MIC", category_id: "c3" }],
}));

const previewRequests: unknown[] = [];
vi.mock("../hooks/use-naming-changes", () => ({
  usePreviewNamingChange: () => ({
    mutate: (req: unknown, opts?: { onSuccess?: () => void }) => {
      previewRequests.push(req);
      opts?.onSuccess?.();
    },
    data: { changes: [], collisions: [] },
    isPending: false,
  }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/protocol-categories" }));
vi.mock("../hooks/use-protocol-forms", () => ({
  useProtocolForms: () => ({ data: state.forms, isLoading: false }),
}));
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
    create.mockReset();
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
    // Saving a pattern first previews the protocols it renames; Apply saves.
    expect(previewRequests.at(-1)).toEqual({
      kind: "category",
      category_id: "c2",
      name_pattern: "{discriminator?} solubility",
    });
    expect(update).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(update).toHaveBeenCalledWith({
      label: "Solubility",
      name_pattern: "{discriminator?} solubility",
    });
  });

  it("sends the category new protocols should start like", async () => {
    render(<ProtocolCategoryAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /^add category$/i }));
    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "Gametocytocidal activity" },
    });
    fireEvent.click(screen.getByRole("combobox"));
    // Only categories that have a form to copy are offered.
    expect(screen.queryByRole("option", { name: "Cytotoxicity" })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("option", { name: "Growth inhibition" }));
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        label: "Gametocytocidal activity",
        name_pattern: null,
        start_like_category_id: "c3",
      }),
    );
  });
});
