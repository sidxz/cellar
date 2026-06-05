import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PreviewStep } from "./preview-step";

const result = {
  outcomes: [
    {
      row_index: 0,
      status: "resolved",
      molecule_id: "m1",
      molecule_name: "Phenol",
    },
    { row_index: 1, status: "unregistered", message: "not_found" },
  ],
  resolved_count: 1,
  already_present_count: 0,
  unregistered_count: 1,
  ambiguous_count: 0,
  error_count: 0,
  preview_id: "p1",
};

describe("PreviewStep", () => {
  it("renders count badges", () => {
    render(<PreviewStep result={result as any} collectionId="c1" onCommit={vi.fn()} />);
    expect(screen.getByText(/1 resolved/i)).toBeInTheDocument();
    expect(screen.getByText(/1 unregistered/i)).toBeInTheDocument();
  });

  it("renders the Register them handoff link when preview_id is present", () => {
    render(<PreviewStep result={result as any} collectionId="c1" onCommit={vi.fn()} />);
    const link = screen.getByRole("link", { name: /register them/i });
    // Opens registration in a new tab so this import tab keeps its rows; only
    // from_collection_import is carried (the wizard re-checks client-side).
    expect(link).toHaveAttribute("href", "/compounds/register?from_collection_import=p1");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("re-checks via onRecheck when there are unregistered rows", () => {
    const onRecheck = vi.fn();
    render(
      <PreviewStep
        result={result as any}
        collectionId="c1"
        onCommit={vi.fn()}
        onRecheck={onRecheck}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /re-check/i }));
    expect(onRecheck).toHaveBeenCalled();
  });

  it("enables commit button only when resolved_count > 0", () => {
    render(<PreviewStep result={result as any} collectionId="c1" onCommit={vi.fn()} />);
    // There are two commit buttons (top + bottom); both should be enabled.
    const buttons = screen.getAllByRole("button", { name: /add 1 resolved/i });
    expect(buttons.length).toBeGreaterThan(0);
    for (const b of buttons) {
      expect(b).toBeEnabled();
    }
  });
});
