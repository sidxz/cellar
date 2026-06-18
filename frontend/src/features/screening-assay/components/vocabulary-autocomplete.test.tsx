import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { VocabularyAutocomplete } from "./vocabulary-autocomplete";

// Radix Popover portals its content and uses pointer/scroll APIs that jsdom
// does not implement. Polyfill so the open/render/click flow works under test.
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
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  }
});

vi.mock("../hooks/use-protocol-vocabulary", () => ({
  useProtocolVocabulary: () => ({ data: ["% Inhibition", "IC50"] }),
}));

describe("VocabularyAutocomplete", () => {
  it("shows existing values and fires onChange on select", () => {
    const onChange = vi.fn();
    render(
      <VocabularyAutocomplete
        value="IC"
        onChange={onChange}
        placeholder="name"
        field="readout_name"
      />,
    );
    fireEvent.focus(screen.getByPlaceholderText("name"));
    fireEvent.click(screen.getByText("IC50"));
    expect(onChange).toHaveBeenCalledWith("IC50");
  });
});
