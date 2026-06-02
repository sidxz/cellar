import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TagFilter } from "./tag-filter";
import type { TagFilterValue } from "./tag-filter";

// Radix Popover/Command items need pointer-event stubs in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

vi.mock("../hooks/use-tags", () => ({
  useTags: () => ({
    data: [
      { id: "tag-1", key: "assay", value: "primary", workspace_id: "w", created_by: "u", created_at: "" },
      { id: "tag-2", key: "status", value: "hit", workspace_id: "w", created_by: "u", created_at: "" },
    ],
  }),
}));

describe("TagFilter", () => {
  const defaultValue: TagFilterValue = { tagIds: [], tagLogic: "any" };

  it("trigger shows 'Tags' when no tags selected", () => {
    render(<TagFilter value={defaultValue} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^tags$/i })).toBeInTheDocument();
  });

  it("trigger shows count when tags are selected", () => {
    render(
      <TagFilter
        value={{ tagIds: ["tag-1"], tagLogic: "any" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /tags \(1\)/i })).toBeInTheDocument();
  });

  it("clicking trigger opens the popover and shows tag options", () => {
    render(<TagFilter value={defaultValue} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /^tags$/i }));
    // TagChip renders the key text; both tags should appear
    expect(screen.getByText("assay")).toBeInTheDocument();
    expect(screen.getByText("status")).toBeInTheDocument();
  });

  it("clicking a tag item calls onChange with that tag's id in tagIds", () => {
    const onChange = vi.fn();
    render(<TagFilter value={defaultValue} onChange={onChange} />);
    // Open the popover
    fireEvent.click(screen.getByRole("button", { name: /^tags$/i }));
    // Click the first tag chip
    const tagItem = screen.getByText("assay").closest("[data-slot='command-item']") as HTMLElement;
    expect(tagItem).not.toBeNull();
    fireEvent.click(tagItem);
    expect(onChange).toHaveBeenCalledWith({ tagIds: ["tag-1"], tagLogic: "any" });
  });

  it("clicking a selected tag deselects it", () => {
    const onChange = vi.fn();
    render(
      <TagFilter
        value={{ tagIds: ["tag-1"], tagLogic: "any" }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /tags \(1\)/i }));
    const tagItem = screen.getByText("assay").closest("[data-slot='command-item']") as HTMLElement;
    fireEvent.click(tagItem);
    expect(onChange).toHaveBeenCalledWith({ tagIds: [], tagLogic: "any" });
  });
});
