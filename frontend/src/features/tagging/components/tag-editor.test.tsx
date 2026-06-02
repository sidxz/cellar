import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const assignMutate = vi.fn().mockResolvedValue({});
const unassignMutate = vi.fn();

vi.mock("../hooks/use-entity-tags", () => ({
  useEntityTags: () => ({
    data: [
      {
        id: "t1",
        key: "project",
        value: "alpha",
        workspace_id: "w",
        created_by: "u",
        created_at: "",
      },
    ],
    isLoading: false,
  }),
  useAssignTag: () => ({ mutateAsync: assignMutate, isPending: false }),
  useUnassignTag: () => ({ mutate: unassignMutate, isPending: false }),
}));
vi.mock("../hooks/use-tags", () => ({ useTags: () => ({ data: [] }) }));

import { TagEditor } from "./tag-editor";

describe("TagEditor", () => {
  beforeEach(() => {
    assignMutate.mockClear();
    unassignMutate.mockClear();
  });

  it("shows existing tags and removes on ×", () => {
    render(<TagEditor entity="collections" entityId="c1" />);
    expect(screen.getByText("project")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove project=alpha/i }));
    expect(unassignMutate).toHaveBeenCalledWith("t1");
  });

  it("assigns a new tag via the key field + Add", async () => {
    render(<TagEditor entity="collections" entityId="c1" />);
    fireEvent.change(screen.getByPlaceholderText("key"), { target: { value: "assay" } });
    fireEvent.click(screen.getByRole("button", { name: /add/i }));
    await Promise.resolve();
    expect(assignMutate).toHaveBeenCalledWith({ key: "assay", value: null });
  });

  it("hides the add form when canEdit is false", () => {
    render(<TagEditor entity="collections" entityId="c1" canEdit={false} />);
    expect(screen.queryByPlaceholderText("key")).not.toBeInTheDocument();
  });
});
