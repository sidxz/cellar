import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AggregationControl } from "./aggregation-control";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill both so
// the test can exercise the open/close + item-click flow that radix-ui's
// Select uses under the hood.
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

describe("AggregationControl", () => {
  it("renders the current mode in the trigger", () => {
    render(<AggregationControl mode="gmean" onChange={vi.fn()} />);
    expect(screen.getByRole("combobox").textContent).toMatch(/Geometric mean/);
  });

  it("calls onChange when a new mode is picked", () => {
    const onChange = vi.fn();
    render(<AggregationControl mode="latest" onChange={onChange} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText(/Best fit/));
    expect(onChange).toHaveBeenCalledWith("best_r2");
  });

  it("renders all four modes in the menu", () => {
    render(<AggregationControl mode="latest" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("combobox"));
    // Radix Select renders the current value in the trigger too, so the
    // currently-selected label ("Latest run") appears twice. Each label
    // is found at least once.
    expect(screen.getAllByText(/Latest run/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Geometric mean/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Arithmetic mean/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Best fit/).length).toBeGreaterThan(0);
  });
});
