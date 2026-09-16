import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

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
  it("hides entirely when there are no protocols to color by", () => {
    const { container } = render(
      <ScaffoldColorPicker protocols={[]} value={null} onChange={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
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
    // Radix Select renders the dropdown items into a portal; "none" appears
    // inside it once the combobox is opened.
    const noneItems = screen.getAllByText(/^none$/i);
    fireEvent.click(noneItems[noneItems.length - 1]);
    expect(handle).toHaveBeenCalledWith(null);
  });
});
