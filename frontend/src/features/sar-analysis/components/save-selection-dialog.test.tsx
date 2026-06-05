import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SaveSelectionDialog } from "./save-selection-dialog";

describe("SaveSelectionDialog", () => {
  it("prefills the name from defaultName", () => {
    render(
      <SaveSelectionDialog
        open
        onClose={() => {}}
        onSave={async () => {}}
        selectedMolecules={[{ id: "a", name: "X", reg_number: "R-1" } as any]}
        defaultName="Diversify-5 from My Set"
        projects={[{ id: "p1", name: "P1" }]}
        defaultProjectId="p1"
      />,
    );
    expect(screen.getByDisplayValue(/Diversify-5 from My Set/)).toBeInTheDocument();
  });

  it("calls onSave with name + projectId + ids", async () => {
    const onSave = vi.fn();
    render(
      <SaveSelectionDialog
        open
        onClose={() => {}}
        onSave={onSave}
        selectedMolecules={[{ id: "a", name: "X", reg_number: "R-1" } as any, { id: "b" } as any]}
        defaultName="My collection"
        projects={[{ id: "p1", name: "P1" }]}
        defaultProjectId="p1"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save & open/i }));
    expect(onSave).toHaveBeenCalledWith({
      name: "My collection",
      projectId: "p1",
      moleculeIds: ["a", "b"],
    });
  });
});
