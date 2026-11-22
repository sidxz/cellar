import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CampaignResultResponse } from "../../types";
import { NotesCell } from "./notes-cell";

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => () => "Ada",
}));

function makeResult(notes: string | null, stamped = notes !== null): CampaignResultResponse {
  return {
    id: "r-1",
    molecule_id: "mol-1",
    notes,
    notes_edited_by: stamped ? "u-1" : null,
    notes_edited_at: stamped ? "2026-11-21T14:03:00Z" : null,
    measurements: [],
    stage_outcomes: [],
  };
}

function renderCell(result: CampaignResultResponse, readOnly: boolean) {
  const onEdit = vi.fn();
  const onHistory = vi.fn();
  render(<NotesCell result={result} readOnly={readOnly} onEdit={onEdit} onHistory={onHistory} />);
  return { onEdit, onHistory };
}

describe("NotesCell", () => {
  it("shows the note in the body text, with who saved it and when under it", () => {
    renderCell(makeResult("Resynthesise before confirming"), false);
    expect(screen.getByText("Resynthesise before confirming")).toHaveClass("text-foreground");
    expect(screen.getByText(/^Ada · /)).toBeInTheDocument();
  });

  it("counts the versions of a changed note, and the count opens its history", () => {
    const { onHistory } = renderCell({ ...makeResult("Third take"), notes_version_count: 3 }, true);
    fireEvent.click(screen.getByRole("button", { name: "· 3 versions" }));
    expect(onHistory).toHaveBeenCalled();
  });

  it("says nothing about versions for a note saved once", () => {
    renderCell({ ...makeResult("First take"), notes_version_count: 1 }, false);
    expect(screen.queryByText(/versions/)).toBeNull();
  });

  it("shows a dash in an empty cell", () => {
    renderCell(makeResult(null), true);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("says a removed note has history", () => {
    renderCell({ ...makeResult(null, true), notes_version_count: 2 }, true);
    expect(screen.getByText("Note removed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "· 2 versions" })).toBeInTheDocument();
  });

  it("shows no stamp under a note that predates tracking", () => {
    renderCell(makeResult("Old note", false), false);
    expect(screen.queryByText(/Ada/)).toBeNull();
  });

  it("an editor clicks the note to edit it", () => {
    const { onEdit } = renderCell(makeResult("Resynthesise"), false);
    fireEvent.click(screen.getByRole("button", { name: "Edit note" }));
    expect(onEdit).toHaveBeenCalled();
  });

  it("an editor right-clicks an empty cell to add a note", () => {
    const { onEdit } = renderCell(makeResult(null), false);
    fireEvent.contextMenu(screen.getByRole("button", { name: "Add note" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Add note…" }));
    expect(onEdit).toHaveBeenCalled();
  });

  it("a viewer right-clicks for the history, never an edit", () => {
    const { onHistory } = renderCell(makeResult("Resynthesise"), true);
    fireEvent.contextMenu(screen.getByText("Resynthesise"));
    expect(screen.queryByRole("menuitem", { name: /note…$/ })).toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: "Note history…" }));
    expect(onHistory).toHaveBeenCalled();
  });

  it("a viewer's empty cell offers no menu", () => {
    renderCell(makeResult(null), true);
    fireEvent.contextMenu(screen.getByText("—"));
    expect(screen.queryByRole("menuitem")).toBeNull();
  });
});
