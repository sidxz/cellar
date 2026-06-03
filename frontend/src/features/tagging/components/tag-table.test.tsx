import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
        assigned_by: "u-jane",
        assigned_at: "2020-06-15T12:00:00Z",
      },
    ],
    isLoading: false,
  }),
  useAssignTag: () => ({ mutateAsync: assignMutate, isPending: false }),
  useUnassignTag: () => ({ mutate: unassignMutate, isPending: false }),
}));
vi.mock("../hooks/use-tags", () => ({ useTags: () => ({ data: [] }) }));
vi.mock("@/shared/components/entity-name", () => ({
  MemberName: ({ id }: { id: string }) => <span>{`member:${id}`}</span>,
}));

import { TagTable } from "./tag-table";

describe("TagTable", () => {
  beforeEach(() => {
    assignMutate.mockClear();
    unassignMutate.mockClear();
  });

  it("shows existing tags as rows (key + value)", () => {
    render(<TagTable entity="collections" entityId="c1" />);
    expect(screen.getByText("project")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });

  it("shows assignment provenance (when + by whom)", () => {
    render(<TagTable entity="collections" entityId="c1" />);
    expect(screen.getByText("member:u-jane")).toBeInTheDocument();
    // old assigned_at → formatRelativeDate falls back to an absolute date
    expect(screen.getByText(/2020/)).toBeInTheDocument();
  });

  it("removes a tag on ×", () => {
    render(<TagTable entity="collections" entityId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: /remove project=alpha/i }));
    expect(unassignMutate).toHaveBeenCalledWith("t1");
  });

  it("reveals the inline add-row only on '+ New tag' and assigns", async () => {
    render(<TagTable entity="collections" entityId="c1" />);
    expect(screen.queryByPlaceholderText("key")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /new tag/i }));
    fireEvent.change(screen.getByPlaceholderText("key"), { target: { value: "assay" } });
    fireEvent.click(screen.getByRole("button", { name: /add tag/i }));

    await waitFor(() => expect(assignMutate).toHaveBeenCalledWith({ key: "assay", value: null }));
  });

  it("is collapsible and open by default", () => {
    render(<TagTable entity="collections" entityId="c1" />);
    const toggle = screen.getByRole("button", { name: /toggle tags/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("hides add + remove affordances when canEdit is false", () => {
    render(<TagTable entity="collections" entityId="c1" canEdit={false} />);
    expect(screen.queryByRole("button", { name: /new tag/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });
});
