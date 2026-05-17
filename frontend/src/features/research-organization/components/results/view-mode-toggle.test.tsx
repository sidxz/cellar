import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ViewModeToggle } from "./view-mode-toggle";

describe("ViewModeToggle", () => {
  it("renders both mode buttons", () => {
    render(<ViewModeToggle mode="cards" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /table view/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /card view/i })).toBeInTheDocument();
  });

  it("highlights the currently-active mode via aria-pressed", () => {
    render(<ViewModeToggle mode="cards" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /card view/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /table view/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onChange with the new mode when the inactive button is clicked", () => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode="cards" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    expect(onChange).toHaveBeenCalledWith("table");
  });

  it("does NOT call onChange when the already-active button is clicked", () => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode="cards" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /card view/i }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
