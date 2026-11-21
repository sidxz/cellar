import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
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

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderCell(result: CampaignResultResponse, readOnly: boolean) {
  return render(<NotesCell campaignId="c-1" result={result} readOnly={readOnly} />, { wrapper });
}

describe("NotesCell", () => {
  it("shows who saved the note and when under it", () => {
    renderCell(makeResult("Resynthesise before confirming"), false);
    expect(screen.getByText(/^by Ada · /)).toBeInTheDocument();
  });

  it("shows no stamp under a note that predates tracking", () => {
    renderCell(makeResult("Old note", false), false);
    expect(screen.queryByText(/^by /)).toBeNull();
  });

  it("a read-only cell with a note opens its history, never an edit", () => {
    renderCell(makeResult("Resynthesise before confirming"), true);
    expect(screen.getByText("Resynthesise before confirming")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Note history" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit notes" })).toBeNull();
  });

  it("a read-only cell whose note was removed says so, and opens its history", () => {
    renderCell(
      { ...makeResult(null), notes_edited_by: "u-1", notes_edited_at: "2026-11-21T14:03:00Z" },
      true,
    );
    const button = screen.getByRole("button", { name: "Note history" });
    expect(button).toHaveTextContent("Note removed");
  });

  it("a read-only empty row with no stamp renders nothing", () => {
    const { container } = renderCell(makeResult(null), true);
    expect(container.textContent).toBe("");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders the notes inside an edit button for an editor", () => {
    renderCell(makeResult("Resynthesise before confirming"), false);
    const button = screen.getByRole("button", { name: "Edit notes" });
    expect(button).toHaveTextContent("Resynthesise before confirming");
  });

  it("shows an Add note affordance for empty notes for an editor", () => {
    renderCell(makeResult(null), false);
    expect(screen.getByRole("button", { name: "Edit notes" })).toBeInTheDocument();
    expect(screen.getByText("Add note")).toBeInTheDocument();
  });
});
