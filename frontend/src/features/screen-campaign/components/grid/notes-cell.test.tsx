import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { CampaignResultResponse } from "../../types";
import { NotesCell } from "./notes-cell";

function makeResult(notes: string | null): CampaignResultResponse {
  return {
    id: "r-1",
    molecule_id: "mol-1",
    notes,
    measurements: [],
    stage_outcomes: [],
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderCell(notes: string | null, readOnly: boolean) {
  return render(<NotesCell campaignId="c-1" result={makeResult(notes)} readOnly={readOnly} />, {
    wrapper,
  });
}

describe("NotesCell", () => {
  it("renders the notes text with no edit affordance when read-only", () => {
    renderCell("Resynthesise before confirming", true);
    expect(screen.getByText("Resynthesise before confirming")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders nothing for empty notes when read-only", () => {
    const { container } = renderCell(null, true);
    expect(container.textContent).toBe("");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders the notes inside an edit button in a draft campaign", () => {
    renderCell("Resynthesise before confirming", false);
    const button = screen.getByRole("button", { name: "Edit notes" });
    expect(button).toHaveTextContent("Resynthesise before confirming");
  });

  it("shows an Add note affordance for empty notes in a draft campaign", () => {
    renderCell(null, false);
    expect(screen.getByRole("button", { name: "Edit notes" })).toBeInTheDocument();
    expect(screen.getByText("Add note")).toBeInTheDocument();
  });
});
