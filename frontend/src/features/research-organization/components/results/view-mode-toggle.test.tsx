import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ViewModeToggle } from "./view-mode-toggle";

describe("ViewModeToggle", () => {
  it("renders both mode buttons", () => {
    render(<ViewModeToggle mode="cards" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /list view/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /grid view/i })).toBeInTheDocument();
  });

  it("highlights the currently-active mode via aria-pressed", () => {
    render(<ViewModeToggle mode="cards" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /grid view/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /list view/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("calls onChange with the new mode when the inactive button is clicked", () => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode="cards" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /list view/i }));
    expect(onChange).toHaveBeenCalledWith("table");
  });

  it("does NOT call onChange when the already-active button is clicked", () => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode="cards" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /grid view/i }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("renders the tree-view segment button", () => {
    render(<ViewModeToggle mode="cards" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /scaffold view/i })).toBeInTheDocument();
  });

  it("highlights tree segment via aria-pressed when mode=scaffold-tree", () => {
    render(<ViewModeToggle mode="scaffold-tree" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /scaffold view/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /grid view/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: /list view/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("calls onChange with 'scaffold-tree' when tree segment is clicked from cards mode", () => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode="cards" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /scaffold view/i }));
    expect(onChange).toHaveBeenCalledWith("scaffold-tree");
  });

  it("does NOT call onChange when tree segment is clicked while already in scaffold-tree mode", () => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode="scaffold-tree" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /scaffold view/i }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
