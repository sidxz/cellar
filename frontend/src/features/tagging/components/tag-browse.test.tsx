import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// Drive the active tag via ?tag=tag-1 so results render without the picker.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("tag=tag-1"),
}));

// next/link → plain anchor so href is assertable in jsdom.
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// The picker is covered by tag-filter.test.tsx; stub it here.
vi.mock("./tag-filter", () => ({ TagFilter: () => null }));

// Cross-type result set for one tag — includes the nested-route Campaign.
const mockRows = [
  { entity_type: "Project", entity_id: "p1", label: "Kinase Project" },
  { entity_type: "Collection", entity_id: "c1", label: "Hit Collection" },
  { entity_type: "Run", entity_id: "r1", label: "AssayProto · 2026-06-04" },
  { entity_type: "Campaign", entity_id: "cmp1", label: "Lead Campaign" },
  { entity_type: "Batch", entity_id: "b1", label: "BT-1" },
];

vi.mock("../hooks/use-tag-entities", () => ({
  useTagEntities: () => ({ data: mockRows, isLoading: false }),
}));

import { TagBrowse } from "./tag-browse";

describe("TagBrowse", () => {
  it("groups tagged entities by type with counts", () => {
    render(<TagBrowse />);
    expect(screen.getByText("Project (1)")).toBeInTheDocument();
    expect(screen.getByText("Collection (1)")).toBeInTheDocument();
    expect(screen.getByText("Run (1)")).toBeInTheDocument();
    expect(screen.getByText("Campaign (1)")).toBeInTheDocument();
    expect(screen.getByText("Batch (1)")).toBeInTheDocument();
  });

  it("links entities that have a flat detail route to that route", () => {
    render(<TagBrowse />);
    expect(screen.getByText("Kinase Project").closest("a")).toHaveAttribute("href", "/projects/p1");
    expect(screen.getByText("BT-1").closest("a")).toHaveAttribute("href", "/inventory/batches/b1");
    // The Run label exercises the backend's non-trivial composed label too.
    expect(screen.getByText("AssayProto · 2026-06-04").closest("a")).toHaveAttribute(
      "href",
      "/assays/runs/r1",
    );
  });

  it("renders Campaign as a non-clickable label (nested route, no projectId in v1)", () => {
    render(<TagBrowse />);
    const campaign = screen.getByText("Lead Campaign");
    expect(campaign.closest("a")).toBeNull();
    expect(campaign.tagName).toBe("SPAN");
  });
});
