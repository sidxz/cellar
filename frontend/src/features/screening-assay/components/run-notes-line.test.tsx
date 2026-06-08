import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Run } from "../types";
import { RunNotesLine } from "./run-notes-line";

// Stub the update mutation so the component renders without a QueryClient.
const mutate = vi.fn();
vi.mock("../hooks/use-runs", () => ({
  useUpdateRun: () => ({ mutate, isPending: false }),
}));

const run = (over: Partial<Run> = {}): Run => ({ id: "r1", notes: null, ...over }) as Run;

describe("RunNotesLine", () => {
  it("renders nothing for a read-only viewer with no notes", () => {
    const { container } = render(<RunNotesLine run={run()} canEdit={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders plain notes text for a read-only viewer", () => {
    render(<RunNotesLine run={run({ notes: "DMSO 0.5%" })} canEdit={false} />);
    expect(screen.getByText("DMSO 0.5%")).toBeInTheDocument();
    // No edit affordance for read-only viewers.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers an 'Add notes…' affordance when editable and empty", () => {
    render(<RunNotesLine run={run()} canEdit />);
    expect(screen.getByRole("button", { name: "Add notes" })).toBeInTheDocument();
    expect(screen.getByText("Add notes…")).toBeInTheDocument();
  });

  it("enters edit mode on click and exposes a textarea", () => {
    render(<RunNotesLine run={run({ notes: "resuspended" })} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Edit notes" }));
    const textarea = screen.getByRole("textbox");
    expect(textarea).toHaveValue("resuspended");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});
