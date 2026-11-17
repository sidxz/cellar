import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const PA = "aaaaaaaa-0000-4000-8000-000000000001";
const PB = "bbbbbbbb-0000-4000-8000-000000000002";
const PC = "cccccccc-0000-4000-8000-000000000003";
const PD = "dddddddd-0000-4000-8000-000000000004";
const summaries = [
  { id: PA, name: "NadD HTS", status: "published", protocol_type: "x", run_count: 3 },
  { id: PB, name: "MMP2 counter", status: "published", protocol_type: "x", run_count: 2 },
  { id: PC, name: "Kinase panel", status: "draft", protocol_type: "x", run_count: 0 },
  { id: PD, name: "Solubility", status: "published", protocol_type: "x", run_count: 1 },
];
const runs = [
  { id: "r1", run_date: "2026-11-12", status: "approved" },
  { id: "r2", run_date: "2026-11-05", status: "completed" },
].map((r) => ({ ...r, created_at: "1", operator: "u1", plate_count: 1, conditions: null }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => () => "A. Chen",
}));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({ data: summaries, isLoading: false }),
  useProtocol: (id: string) => ({ data: summaries.find((p) => p.id === id) }),
}));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: runs, isLoading: false }),
}));
vi.mock("../hooks/use-run-row-counts", () => ({
  useRunRowCounts: () => ({ data: { counts: { r1: 96, r2: 96 } } }),
}));

import { AddProtocolDialog } from "./add-protocol-dialog";

// cmdk needs this in jsdom.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
});

const open = (onAdd = vi.fn()) => {
  render(<AddProtocolDialog open onOpenChange={vi.fn()} exclude={[PA]} onAdd={onAdd} />);
  return onAdd;
};

describe("AddProtocolDialog", () => {
  it("lists protocols by name with their runs, hiding the ones already loaded", () => {
    open();
    const dialog = screen.getByRole("dialog", { name: "Add a protocol" });
    expect(screen.getByRole("option", { name: /MMP2 counter/ })).toHaveTextContent("2 runs");
    expect(screen.queryByRole("option", { name: /NadD HTS/ })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Kinase panel/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("option", { name: /Kinase panel/ })).toHaveTextContent("No runs");
    expect(dialog.textContent).not.toMatch(UUID);
  });

  it("adds a protocol with every run", () => {
    const onAdd = open();
    fireEvent.click(screen.getByRole("option", { name: /MMP2 counter/ }));
    expect(screen.getByRole("dialog", { name: "Choose runs to visualize" })).toHaveTextContent(
      "MMP2 counter",
    );
    fireEvent.click(screen.getByRole("button", { name: "Add protocol" }));
    expect(onAdd).toHaveBeenCalledWith({ protocolId: PB });
  });

  it("adds a protocol with the runs chosen", () => {
    const onAdd = open();
    fireEvent.click(screen.getByRole("option", { name: /MMP2 counter/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Include 2026-11-12 · A. Chen" }));
    fireEvent.click(screen.getByRole("button", { name: "Add protocol" }));
    expect(onAdd).toHaveBeenCalledWith({ protocolId: PB, runIds: ["r2"] });
  });
});
