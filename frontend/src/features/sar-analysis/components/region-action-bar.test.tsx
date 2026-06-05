import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RegionActionBar } from "./region-action-bar";

const baseProps = {
  regionCount: 12,
  n: 5,
  onNChange: vi.fn(),
  onPickDiverse: vi.fn(),
  picking: false,
  pickCount: 0,
  onAddPicks: vi.fn(),
  onAddAll: vi.fn(),
  onRemove: vi.fn(),
  onClear: vi.fn(),
};

describe("RegionActionBar", () => {
  it("shows the region count", () => {
    render(<RegionActionBar {...baseProps} />);
    expect(screen.getByText(/12 in region/i)).toBeInTheDocument();
  });

  it("Add picks is disabled until there are picks", () => {
    render(<RegionActionBar {...baseProps} pickCount={0} />);
    expect(screen.getByRole("button", { name: /add picks/i })).toBeDisabled();
  });

  it("Add picks enables and reports the pick count", () => {
    render(<RegionActionBar {...baseProps} pickCount={3} />);
    const btn = screen.getByRole("button", { name: /add picks \(3\)/i });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(baseProps.onAddPicks).toHaveBeenCalled();
  });

  it("Add all reports the region count and fires", () => {
    render(<RegionActionBar {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /add all \(12\)/i }));
    expect(baseProps.onAddAll).toHaveBeenCalled();
  });

  it("Pick diverse fires and is disabled while picking", () => {
    const { rerender } = render(<RegionActionBar {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /pick diverse/i }));
    expect(baseProps.onPickDiverse).toHaveBeenCalled();
    rerender(<RegionActionBar {...baseProps} picking />);
    expect(screen.getByRole("button", { name: /picking/i })).toBeDisabled();
  });
});
