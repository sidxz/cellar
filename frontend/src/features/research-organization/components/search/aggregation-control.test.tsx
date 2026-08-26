import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

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

  // The `disabled` prop swaps the dropdown for a static label (used when
  // every activity criterion narrows scope to one run and any aggregation
  // rule is a no-op). The behavior contract: no interactive combobox is
  // rendered, so chemists can't trigger a useless re-fetch.
  it("renders no combobox when disabled (so onChange can never fire)", () => {
    const onChange = vi.fn();
    render(<AggregationControl mode="gmean" onChange={onChange} disabled />);
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });
});
