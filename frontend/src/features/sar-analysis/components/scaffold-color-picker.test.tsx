import { beforeAll, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ScaffoldColorPicker } from "./scaffold-color-picker";

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

describe("ScaffoldColorPicker", () => {
  it("renders 'none' label by default", () => {
    render(
      <ScaffoldColorPicker
        protocols={[{ id: "p1", name: "Mtb WCA" }]}
        value={null}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/— none —/i)).toBeInTheDocument();
  });

  it("emits onChange when a protocol is picked", () => {
    const handle = vi.fn();
    render(
      <ScaffoldColorPicker
        protocols={[{ id: "p1", name: "Mtb WCA" }]}
        value={null}
        onChange={handle}
      />,
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("Mtb WCA"));
    expect(handle).toHaveBeenCalledWith("p1");
  });

  it("clears back to null via the 'none' option", () => {
    const handle = vi.fn();
    render(
      <ScaffoldColorPicker
        protocols={[{ id: "p1", name: "Mtb WCA" }]}
        value="p1"
        onChange={handle}
      />,
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText(/— none —/i));
    expect(handle).toHaveBeenCalledWith(null);
  });
});
