import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const unassignMutate = vi.fn();
let tagsData: Array<{
  id: string;
  key: string;
  value: string | null;
  assigned_at: string;
  assigned_by: string;
}> = [];

vi.mock("../hooks/use-entity-tags", () => ({
  useEntityTags: () => ({ data: tagsData, isLoading: false }),
  useAssignTag: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUnassignTag: () => ({ mutate: unassignMutate }),
}));
vi.mock("../hooks/use-tags", () => ({ useTags: () => ({ data: [] }) }));

import { TagChips } from "./tag-chips";

describe("TagChips", () => {
  it("renders nothing when there are no tags and the viewer cannot edit", () => {
    tagsData = [];
    const { container } = render(<TagChips entity="campaigns" entityId="c1" canEdit={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the + Tag pill with no tags when editable", () => {
    tagsData = [];
    render(<TagChips entity="campaigns" entityId="c1" canEdit />);
    expect(screen.getByRole("button", { name: /Tag/ })).toBeInTheDocument();
  });

  it("renders chips; remove buttons only when editable", () => {
    tagsData = [
      {
        id: "t1",
        key: "series",
        value: "A",
        assigned_at: "2026-09-11T00:00:00Z",
        assigned_by: "u",
      },
      {
        id: "t2",
        key: "priority",
        value: null,
        assigned_at: "2026-09-11T00:00:00Z",
        assigned_by: "u",
      },
    ];
    const { rerender } = render(<TagChips entity="campaigns" entityId="c1" canEdit={false} />);
    expect(screen.getByText("series")).toBeInTheDocument();
    expect(screen.getByText("priority")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();

    rerender(<TagChips entity="campaigns" entityId="c1" canEdit />);
    expect(screen.getAllByRole("button", { name: /Remove/ })).toHaveLength(2);
  });
});
