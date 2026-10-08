import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Protocol } from "../../types";
import { OverviewTab } from "./overview-tab";

vi.mock("../../hooks/use-protocol-stats", () => ({
  useProtocolStats: () => ({ data: undefined, isLoading: false }),
}));
vi.mock("../../hooks/use-protocol-collection-coverage", () => ({
  useProtocolCollectionCoverage: () => ({ data: undefined }),
}));
vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => false }));
vi.mock("@/features/tagging/components/tag-table", () => ({ TagTable: () => null }));
vi.mock("../protocol-aliases-card", () => ({ ProtocolAliasesCard: () => null }));

function protocol(over: Partial<Protocol> = {}): Protocol {
  return {
    id: "p1",
    code: "PRT-00001",
    name: "M. tuberculosis growth inhibition",
    discriminator: null,
    name_flag: null,
    protocol_type: "whole_cell",
    status: "draft",
    description: null,
    category: "Growth inhibition",
    targets: [],
    aliases: [],
    readout_definitions: [],
    condition_definitions: [],
    created_at: "2026-10-08T00:00:00Z",
    ...over,
  } as unknown as Protocol;
}

describe("NameFlagNotice", () => {
  it("needs_facts points to the Design tab", () => {
    const onTabChange = vi.fn();
    render(
      <OverviewTab
        protocol={protocol({ name_flag: "needs_facts" })}
        protocolId="p1"
        onTabChange={onTabChange}
      />,
    );
    expect(screen.getByText(/name is missing a field/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /open the design tab/i }));
    expect(onTabChange).toHaveBeenCalledWith("design");
  });

  it.each([
    ["needs_discriminator", /share this name/i],
    ["name_conflict", /exact same name/i],
  ])("%s explains itself", (flag, text) => {
    render(
      <OverviewTab
        protocol={protocol({ name_flag: flag })}
        protocolId="p1"
        onTabChange={vi.fn()}
      />,
    );
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("shows nothing when the name is fine, and the discriminator in details", () => {
    render(
      <OverviewTab
        protocol={protocol({ discriminator: "resazurin" })}
        protocolId="p1"
        onTabChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("resazurin")).toBeInTheDocument();
  });

  it.each(["needs_discriminator", "name_conflict"])(
    "%s offers to edit the discriminator when the protocol can be edited",
    (flag) => {
      const onEditName = vi.fn();
      render(
        <OverviewTab
          protocol={protocol({ name_flag: flag })}
          protocolId="p1"
          onTabChange={vi.fn()}
          onEditName={onEditName}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /discriminator/i }));
      expect(onEditName).toHaveBeenCalled();
    },
  );

  it("offers no edit when the protocol cannot be edited", () => {
    render(
      <OverviewTab
        protocol={protocol({ name_flag: "needs_discriminator" })}
        protocolId="p1"
        onTabChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /discriminator/i })).not.toBeInTheDocument();
  });
});
