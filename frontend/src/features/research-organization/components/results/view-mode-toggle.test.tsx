import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ViewMode } from "../../lib/use-view-mode";
import { ViewModeToggle } from "./view-mode-toggle";

const SEGMENTS: [ViewMode, string][] = [
  ["table", "List view"],
  ["cards", "Grid view"],
  ["scaffold-tree", "Scaffold view"],
  ["clusters", "Cluster view"],
  ["sar", "SAR view"],
];

describe("ViewModeToggle", () => {
  it.each(SEGMENTS)("in %s mode presses only the %s segment", (mode, label) => {
    render(<ViewModeToggle mode={mode} onChange={vi.fn()} />);
    for (const [, other] of SEGMENTS) {
      expect(screen.getByRole("button", { name: other })).toHaveAttribute(
        "aria-pressed",
        String(other === label),
      );
    }
  });

  it.each(SEGMENTS)("switches to %s from another mode", (mode, label) => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode={mode === "cards" ? "table" : "cards"} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: label }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith(mode);
  });

  it.each(SEGMENTS)("does not call onChange when %s is already active", (mode, label) => {
    const onChange = vi.fn();
    render(<ViewModeToggle mode={mode} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: label }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
