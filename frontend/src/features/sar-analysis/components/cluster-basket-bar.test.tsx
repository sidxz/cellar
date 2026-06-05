import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClusterBasketBar } from "./cluster-basket-bar";

const baseProps = {
  count: 0,
  plateTarget: 96,
  repCount: 5,
  onAddRepPicks: vi.fn(),
  onSave: vi.fn(),
  onClear: vi.fn(),
};

describe("ClusterBasketBar", () => {
  it("shows the basket count", () => {
    render(<ClusterBasketBar {...baseProps} count={7} />);
    expect(screen.getByText(/basket: 7/i)).toBeInTheDocument();
  });

  it("shows the plate-target hint only when non-empty", () => {
    const { rerender } = render(<ClusterBasketBar {...baseProps} count={0} />);
    expect(screen.queryByText(/\/ 96/)).not.toBeInTheDocument();
    rerender(<ClusterBasketBar {...baseProps} count={48} />);
    expect(screen.getByText(/48 \/ 96/)).toBeInTheDocument();
  });

  it("Save is disabled when the basket is empty", () => {
    render(<ClusterBasketBar {...baseProps} count={0} />);
    expect(screen.getByRole("button", { name: /save as collection/i })).toBeDisabled();
  });

  it("Save fires when there are compounds", () => {
    render(<ClusterBasketBar {...baseProps} count={3} />);
    fireEvent.click(screen.getByRole("button", { name: /save as collection/i }));
    expect(baseProps.onSave).toHaveBeenCalled();
  });

  it("Add Diversify picks reports the rep count and fires", () => {
    render(<ClusterBasketBar {...baseProps} repCount={5} />);
    fireEvent.click(screen.getByRole("button", { name: /add diversify picks \(5\)/i }));
    expect(baseProps.onAddRepPicks).toHaveBeenCalled();
  });

  it("Clear is disabled when empty and fires when not", () => {
    const { rerender } = render(<ClusterBasketBar {...baseProps} count={0} />);
    expect(screen.getByRole("button", { name: /clear basket/i })).toBeDisabled();
    rerender(<ClusterBasketBar {...baseProps} count={2} />);
    fireEvent.click(screen.getByRole("button", { name: /clear basket/i }));
    expect(baseProps.onClear).toHaveBeenCalled();
  });
});
