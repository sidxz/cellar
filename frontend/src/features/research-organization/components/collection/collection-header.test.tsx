import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CollectionHeader } from "./collection-header";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"}>{children}</a>
  ),
}));

vi.mock("@/shared/components/entity-name", () => ({
  MemberName: ({ id }: { id: string }) => <span data-testid="member">{id}</span>,
}));
vi.mock("@/shared/hooks/use-orgs", () => ({
  useOrgName: () => (id: string | null | undefined) =>
    ({ o1: "TAMU", o2: "Partner Lab" })[id ?? ""] ?? "",
}));
vi.mock("@/shared/components/owner-org-line", () => ({
  OwnerOrgLine: ({ ownerOrgId, canChange }: { ownerOrgId: string; canChange: boolean }) => (
    <span data-testid="owner" data-can-change={String(canChange)}>
      {ownerOrgId}
    </span>
  ),
}));

const baseCollection = {
  id: "c1",
  name: "Mtb Q1 Hits",
  description: "Round 1 hits from Mtb_WCA",
  project_id: "p1",
  owner_org_id: "o2",
  created_by_org_id: "o1",
  created_by: "u1",
  visibility: "shared" as const,
  molecule_count: 30,
  is_frozen: false,
  type: "library" as const,
  derived_from_campaign_id: null,
};

describe("CollectionHeader", () => {
  it("shows project name as a link to the project", () => {
    render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
    const link = screen.getByRole("link", { name: /Mtb-TB/i });
    expect(link).toHaveAttribute("href", "/projects/p1");
  });

  it("renders a 'Frozen' chip when is_frozen=true", () => {
    render(
      <CollectionHeader collection={{ ...baseCollection, is_frozen: true }} projectName="Mtb-TB" />,
    );
    expect(screen.getByText(/frozen/i)).toBeInTheDocument();
  });

  it("renders a campaign provenance link when derived_from_campaign_id is set", () => {
    render(
      <CollectionHeader
        collection={{ ...baseCollection, derived_from_campaign_id: "camp-7" }}
        projectName="Mtb-TB"
      />,
    );
    const link = screen.getByRole("link", { name: /from campaign/i });
    expect(link).toHaveAttribute("href", "/campaigns/camp-7");
  });

  it("shows the owner and lets the creator change it", () => {
    render(<CollectionHeader collection={baseCollection} canChangeOwner onChangeOwner={vi.fn()} />);
    expect(screen.getByTestId("owner")).toHaveTextContent("o2");
    expect(screen.getByTestId("owner")).toHaveAttribute("data-can-change", "true");
  });

  it("another editor sees the owner without a change control", () => {
    render(<CollectionHeader collection={baseCollection} />);
    expect(screen.getByTestId("owner")).toHaveAttribute("data-can-change", "false");
  });

  it("names the creator's org next to the creator", () => {
    render(<CollectionHeader collection={baseCollection} />);
    expect(screen.getByText(/Created by/)).toHaveTextContent("TAMU");
  });
});
