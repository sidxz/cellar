import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { SearchCombobox } from "./search-combobox";

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

interface Row {
  id: string;
  label: string;
}

const ROWS: Row[] = [
  { id: "1", label: "Aspirin" },
  { id: "2", label: "Ibuprofen" },
];

function renderCombobox(overrides: Partial<React.ComponentProps<typeof SearchCombobox<Row>>> = {}) {
  const onSearchChange = vi.fn();
  const onSelect = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <SearchCombobox<Row>
      searchValue=""
      onSearchChange={onSearchChange}
      items={ROWS}
      getItemKey={(r) => r.id}
      renderItem={(r) => <span>{r.label}</span>}
      onSelect={onSelect}
      open
      onOpenChange={onOpenChange}
      placeholder="Search..."
      {...overrides}
    />,
  );
  return { onSearchChange, onSelect, onOpenChange };
}

describe("SearchCombobox", () => {
  it("renders the search input with placeholder", () => {
    renderCombobox({ open: false });
    expect(screen.getByPlaceholderText("Search...")).toBeInTheDocument();
  });

  it("forwards keystrokes through onSearchChange", () => {
    const { onSearchChange } = renderCombobox({ open: false });
    fireEvent.change(screen.getByPlaceholderText("Search..."), { target: { value: "asp" } });
    expect(onSearchChange).toHaveBeenCalledWith("asp");
  });

  it("renders result rows when open", () => {
    renderCombobox();
    expect(screen.getByText("Aspirin")).toBeInTheDocument();
    expect(screen.getByText("Ibuprofen")).toBeInTheDocument();
  });

  it("calls onSelect with the clicked item (explicit selection)", () => {
    const { onSelect } = renderCombobox();
    fireEvent.click(screen.getByText("Ibuprofen"));
    expect(onSelect).toHaveBeenCalledWith(ROWS[1]);
  });

  it("shows the loading message while loading", () => {
    renderCombobox({ isLoading: true, loadingMessage: "Searching…" });
    expect(screen.getByText("Searching…")).toBeInTheDocument();
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
  });

  it("shows the empty message when there are no items", () => {
    renderCombobox({ items: [], emptyMessage: "No compounds found." });
    expect(screen.getByText("No compounds found.")).toBeInTheDocument();
  });

  it("renders a clear button only when onClear is provided", () => {
    const onClear = vi.fn();
    renderCombobox({ open: false, onClear, clearAriaLabel: "Clear selection" });
    const clearBtn = screen.getByRole("button", { name: "Clear selection" });
    fireEvent.click(clearBtn);
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("omits the clear button when onClear is not provided", () => {
    renderCombobox({ open: false });
    expect(screen.queryByRole("button", { name: /clear/i })).not.toBeInTheDocument();
  });

  it("renders a footer node below the list", () => {
    renderCombobox({ footer: <div>+ Free text</div> });
    expect(screen.getByText("+ Free text")).toBeInTheDocument();
  });
});
