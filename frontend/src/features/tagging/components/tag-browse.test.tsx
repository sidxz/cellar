import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("tag=tag-1"),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// The picker is now the shared TagFilter (covered by tag-filter.test.tsx); stub it.
vi.mock("./tag-filter", () => ({ TagFilter: () => null }));

// Avoid AG Grid in jsdom — assert via a stub that renders the rows it receives.
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: ({ rowData }: { rowData: Array<{ entity_id: string; label: string }> }) => (
    <div data-testid="grid">
      {rowData.map((r) => (
        <div key={r.entity_id} data-testid="grid-row">
          {r.label}
        </div>
      ))}
    </div>
  ),
}));

const rows = [
  { entity_type: "Molecule", entity_id: "m1", label: "CC-1", assigned_at: "2026-06-04T00:00:00Z" },
  { entity_type: "Molecule", entity_id: "m2", label: "CC-2", assigned_at: "2026-06-03T00:00:00Z" },
  { entity_type: "Protocol", entity_id: "p1", label: "Proto", assigned_at: "2026-06-02T00:00:00Z" },
];
vi.mock("../hooks/use-tag-entities", () => ({
  useTagEntities: () => ({ data: rows, isLoading: false, error: null }),
}));

import { TagBrowse, hrefFor } from "./tag-browse";

describe("hrefFor", () => {
  it("links flat-route types to their detail page", () => {
    expect(hrefFor({ entity_type: "Molecule", entity_id: "m1" })).toBe("/compounds/m1");
    expect(hrefFor({ entity_type: "Protocol", entity_id: "p1" })).toBe("/assays/protocols/p1");
    expect(hrefFor({ entity_type: "Project", entity_id: "pr1" })).toBe("/projects/pr1");
    expect(hrefFor({ entity_type: "Collection", entity_id: "co1" })).toBe("/collections/co1");
    expect(hrefFor({ entity_type: "Run", entity_id: "r1" })).toBe("/assays/runs/r1");
    expect(hrefFor({ entity_type: "Batch", entity_id: "b1" })).toBe("/inventory/batches/b1");
    expect(hrefFor({ entity_type: "Plate", entity_id: "pl1" })).toBe("/inventory/plates/pl1");
  });

  it("returns null for the nested-route Campaign (not directly linkable)", () => {
    expect(hrefFor({ entity_type: "Campaign", entity_id: "c1" })).toBeNull();
  });
});

describe("TagBrowse", () => {
  it("summarizes results and shows per-type facets", () => {
    render(<TagBrowse />);
    expect(screen.getByText("3 items across 2 types")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Molecule/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Protocol/ })).toBeInTheDocument();
    // All three rows reach the grid before any facet is applied.
    expect(screen.getAllByTestId("grid-row")).toHaveLength(3);
  });

  it("filters the grid to one type when its facet is clicked", () => {
    render(<TagBrowse />);
    fireEvent.click(screen.getByRole("button", { name: /Protocol/ }));
    expect(screen.getAllByTestId("grid-row").map((e) => e.textContent)).toEqual(["Proto"]);
  });
});
