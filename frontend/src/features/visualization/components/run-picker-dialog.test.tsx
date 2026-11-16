import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const names: Record<string, string> = { u1: "A. Chen", u2: "R. Iyer" };
const runs = [
  { id: "r1", run_date: "2026-11-12", created_at: "1", operator: "u1", status: "approved" },
  { id: "r2", run_date: "2026-11-05", created_at: "1", operator: "u2", status: "completed" },
  { id: "r3", run_date: "2026-10-29", created_at: "1", operator: "u1", status: "draft" },
].map((r) => ({ ...r, plate_count: 3, conditions: { ATP: "10 uM" } }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string) => names[id] ?? "",
}));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: runs, isLoading: false }),
}));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocol: () => ({ data: { id: "p1", name: "NadD HTS" } }),
}));
vi.mock("../hooks/use-run-row-counts", () => ({
  useRunRowCounts: () => ({ data: { counts: { r1: 150_000, r2: 40_000, r3: 30_000 } } }),
}));

import { type OpenView, OpenViewContext } from "../store/open-view-context";
import { RunPickerDialog } from "./run-picker-dialog";
import { VisualizeButton } from "./visualize-button";

beforeEach(() => push.mockReset());

describe("RunPickerDialog", () => {
  it("preselects every run and disables Open above the row cap with the reason", () => {
    render(<RunPickerDialog protocolId="p1" open onOpenChange={vi.fn()} />);
    expect(screen.getByText("220,000 wells selected")).toBeInTheDocument();
    expect(screen.getByText(/over the 100,000-row limit/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open workbench" })).toBeDisabled();
    expect(screen.queryByText("Not counted")).not.toBeInTheDocument();
  });

  it("at Compounds, marks runs that don't count there, keeps them ticked and opens at that level", () => {
    render(<RunPickerDialog protocolId="p1" level="compounds" open onOpenChange={vi.fn()} />);
    expect(screen.getByText("Not counted")).toHaveAttribute(
      "title",
      "Batches and Compounds count only completed or approved runs",
    );
    expect(screen.getByRole("checkbox", { name: "Include 2026-10-29 · A. Chen" })).toBeChecked();
    expect(screen.getByText("2 of 3 chosen runs count at this level")).toBeInTheDocument();
    expect(screen.getByText("220,000 wells selected")).toBeInTheDocument();
    expect(screen.queryByText(/over the 100,000-row limit/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open workbench" }));
    expect(push).toHaveBeenCalledWith("/assays/visualize?protocol=p1&level=compounds");
  });

  it("updates the total when a run is unticked and opens the chosen runs", () => {
    render(<RunPickerDialog protocolId="p1" open onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Include 2026-11-12 · A. Chen" }));
    expect(screen.getByText("70,000 wells selected")).toBeInTheDocument();
    expect(screen.queryByText(/over the 100,000-row limit/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open workbench" }));
    expect(push).toHaveBeenCalledWith("/assays/visualize?protocol=p1&runs=r2%2Cr3");
  });

  it("inside a saved view, reopens that view on the chosen runs", () => {
    const open = { view: { id: "v1" }, config: {}, reload: vi.fn() } as unknown as OpenView;
    render(
      <OpenViewContext.Provider value={open}>
        <RunPickerDialog protocolId="p1" open onOpenChange={vi.fn()} />
      </OpenViewContext.Provider>,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Include 2026-11-12 · A. Chen" }));
    fireEvent.click(screen.getByRole("button", { name: "Open workbench" }));
    expect(push).toHaveBeenCalledWith("/assays/visualize/v1?protocol=p1&runs=r2%2Cr3&level=wells");
  });

  it("lists runs as date · operator, never user ids", () => {
    render(<RunPickerDialog protocolId="p1" open onOpenChange={vi.fn()} />);
    const text = screen.getByRole("dialog").textContent ?? "";
    expect(text).toContain("R. Iyer");
    expect(text).not.toMatch(/\bu[12]\b/);
  });
});

describe("VisualizeButton", () => {
  it("links a run straight to the workbench", () => {
    render(<VisualizeButton runId="r9" />);
    expect(screen.getByRole("link", { name: /visualize/i })).toHaveAttribute(
      "href",
      "/assays/visualize?run=r9",
    );
  });

  it("opens the run picker from a protocol", () => {
    render(<VisualizeButton protocolId="p1" />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /visualize/i }));
    expect(screen.getByRole("dialog", { name: "Choose runs to visualize" })).toBeInTheDocument();
  });
});
