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
  OrgName: ({ id }: { id: string }) => <span data-testid="org">{id}</span>,
}));

const baseCollection = {
  id: "c1",
  name: "Mtb Q1 Hits",
  description: "Round 1 hits from Mtb_WCA",
  project_id: "p1",
  owned_by_org_id: "o1",
  created_by: "u1",
  visibility: "shared" as const,
  molecule_count: 30,
  is_frozen: false,
  type: "library" as const,
  derived_from_campaign_id: null,
};

describe("CollectionHeader", () => {
  it("renders the description", () => {
    render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
    expect(screen.getByText(/Round 1 hits/)).toBeInTheDocument();
  });

  it("shows the molecule count badge", () => {
    render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
    expect(screen.getByText(/30 molecules/i)).toBeInTheDocument();
  });

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

  it("renders the visibility chip", () => {
    render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
    expect(screen.getByText(/shared/i)).toBeInTheDocument();
  });

  it("renders the collection type badge", () => {
    render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
    expect(screen.getByText("Library")).toBeInTheDocument();
  });

  it("renders rightSlot content at the right end of the strip", () => {
    render(
      <CollectionHeader
        collection={baseCollection}
        projectName="Mtb-TB"
        rightSlot={<button>extra</button>}
      />,
    );
    expect(screen.getByRole("button", { name: /extra/i })).toBeInTheDocument();
  });
});
