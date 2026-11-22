import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Collection } from "../types";

const h = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn() }));

vi.mock("../hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: h.create, isPending: false }),
  useUpdateCollection: () => ({ mutate: h.update, isPending: false }),
}));
vi.mock("../hooks/use-projects", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("@/shared/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { user_id: "u1", org_id: "org-tamu" } }),
}));
vi.mock("@/shared/components/duar-org-select", () => ({
  DuarOrgSelect: ({ id }: { id?: string }) => <span id={id}>org picker</span>,
}));

import { CreateCollectionDialog } from "./create-collection-dialog";

beforeEach(() => {
  h.create.mockClear();
  h.update.mockClear();
});

describe("CreateCollectionDialog", () => {
  it("create collection sends owner_org_id, defaulting to my org", async () => {
    render(<CreateCollectionDialog open onOpenChange={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText(/EGFR Hit Series/), { target: { value: "Hits" } });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    await waitFor(() => expect(h.create).toHaveBeenCalled());
    expect(h.create.mock.calls[0][0]).toMatchObject({ owner_org_id: "org-tamu" });
  });

  it("edit collection has no org field", async () => {
    const collection = {
      id: "c1",
      name: "Hits",
      description: null,
      project_id: null,
      owner_org_id: "org-tamu",
      visibility: "private",
      type: "generic",
    } as unknown as Collection;
    render(<CreateCollectionDialog open onOpenChange={vi.fn()} collection={collection} />);
    expect(screen.queryByText("Owned by")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(h.update).toHaveBeenCalled());
    expect(h.update.mock.calls[0][0]).not.toHaveProperty("owner_org_id");
  });
});
