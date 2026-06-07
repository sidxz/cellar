import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { SaveExclusionsDialog } from "./save-exclusions-dialog";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test.
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

describe("SaveExclusionsDialog", () => {
  it("renders with the dirty count in the title and button", () => {
    render(<SaveExclusionsDialog open onOpenChange={vi.fn()} onSave={vi.fn()} dirtyCount={3} />);
    expect(screen.getByText(/save 3 exclusion changes/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save 3/i })).toBeInTheDocument();
  });

  it("disables the Save button until a reason is selected", () => {
    render(<SaveExclusionsDialog open onOpenChange={vi.fn()} onSave={vi.fn()} dirtyCount={1} />);
    expect(screen.getByRole("button", { name: /save 1/i })).toBeDisabled();
  });

  it("enables Save once a reason is selected and submits with the right payload", () => {
    const onSave = vi.fn();
    render(<SaveExclusionsDialog open onOpenChange={vi.fn()} onSave={onSave} dirtyCount={2} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText(/outlier/i));
    fireEvent.change(screen.getByLabelText(/note/i), {
      target: { value: "lid dropped on plate" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save 2/i }));
    expect(onSave).toHaveBeenCalledWith({
      reason: "outlier",
      note: "lid dropped on plate",
    });
  });

  it("submits with note=null when textarea is empty", () => {
    const onSave = vi.fn();
    render(<SaveExclusionsDialog open onOpenChange={vi.fn()} onSave={onSave} dirtyCount={1} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText(/contamination/i));
    fireEvent.click(screen.getByRole("button", { name: /save 1/i }));
    expect(onSave).toHaveBeenCalledWith({ reason: "contamination", note: null });
  });

  it("Cancel triggers onOpenChange(false)", () => {
    const onOpenChange = vi.fn();
    render(
      <SaveExclusionsDialog open onOpenChange={onOpenChange} onSave={vi.fn()} dirtyCount={1} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("disables both buttons while isSaving is true", () => {
    render(
      <SaveExclusionsDialog open onOpenChange={vi.fn()} onSave={vi.fn()} dirtyCount={1} isSaving />,
    );
    expect(screen.getByRole("button", { name: /save 1/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });
});
