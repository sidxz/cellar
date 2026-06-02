import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TagChip } from "./tag-chip";

describe("TagChip", () => {
  it("renders key=value", () => {
    render(<TagChip tagKey="project" value="alpha" />);
    expect(screen.getByText("project")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });
  it("renders just the key when value-less", () => {
    render(<TagChip tagKey="favorite" value={null} />);
    expect(screen.getByText("favorite")).toBeInTheDocument();
    expect(screen.queryByText("=")).not.toBeInTheDocument();
  });
  it("calls onRemove when the remove button is clicked", () => {
    const onRemove = vi.fn();
    render(<TagChip tagKey="x" value={null} onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
