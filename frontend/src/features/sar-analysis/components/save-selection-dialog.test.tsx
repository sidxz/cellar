import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SaveSelectionDialog } from "./save-selection-dialog";

describe("SaveSelectionDialog", () => {
  it("prefills the name from defaultName and titles by count", () => {
    render(
      <SaveSelectionDialog
        open
        onOpenChange={() => {}}
        onSave={async () => {}}
        count={3}
        defaultName="Diversify-5 from My Set"
        projects={[{ id: "p1", name: "P1" }]}
        defaultProjectId="p1"
      />,
    );
    expect(screen.getByDisplayValue(/Diversify-5 from My Set/)).toBeInTheDocument();
    expect(screen.getByText(/Save 3 compounds as a new collection/i)).toBeInTheDocument();
  });

  it("calls onSave with name + projectId (no ids)", () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <SaveSelectionDialog
        open
        onOpenChange={() => {}}
        onSave={onSave}
        count={2}
        defaultName="My collection"
        projects={[{ id: "p1", name: "P1" }]}
        defaultProjectId="p1"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save & open/i }));
    expect(onSave).toHaveBeenCalledWith({ name: "My collection", projectId: "p1" });
  });

  it("renders the preview list when preview is provided", () => {
    render(
      <SaveSelectionDialog
        open
        onOpenChange={() => {}}
        onSave={async () => {}}
        count={1}
        preview={[{ id: "a", name: "X", reg_number: "R-1" }]}
        defaultName="c"
        projects={[]}
        defaultProjectId={null}
      />,
    );
    expect(screen.getByText("R-1")).toBeInTheDocument();
  });

  it("disables save when count is 0", () => {
    render(
      <SaveSelectionDialog
        open
        onOpenChange={() => {}}
        onSave={async () => {}}
        count={0}
        defaultName="c"
        projects={[]}
        defaultProjectId={null}
      />,
    );
    expect(screen.getByRole("button", { name: /save & open/i })).toBeDisabled();
  });
});
