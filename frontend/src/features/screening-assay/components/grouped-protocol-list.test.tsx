import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProtocolGroup } from "../lib/protocol-facets";
import type { Protocol } from "../types";
import { GroupedProtocolList } from "./grouped-protocol-list";

const p = (id: string, name: string): Protocol =>
  ({
    id,
    name,
    protocol_type: "biochemical",
    status: "active",
    category: null,
    targets: [],
    readout_definitions: [],
    ontology_annotations: null,
    protocol_version: 1,
  }) as unknown as Protocol;

const groups: ProtocolGroup[] = [
  { key: "t1", label: "RNAP", count: 2, protocols: [p("a", "Alpha"), p("b", "Bravo")] },
  { key: "__none__", label: "No target", count: 1, protocols: [p("c", "Charlie")] },
];

describe("GroupedProtocolList", () => {
  it("renders group headers with counts and member rows", () => {
    render(<GroupedProtocolList groups={groups} groupBy="target" onGroupByChange={vi.fn()} />);
    expect(screen.getByText("RNAP")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("No target")).toBeInTheDocument();
  });

  it("fires onSelect with the protocol id on row click", () => {
    const onSelect = vi.fn();
    render(
      <GroupedProtocolList
        groups={groups}
        groupBy="target"
        onGroupByChange={vi.fn()}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByText("Alpha"));
    expect(onSelect).toHaveBeenCalledWith("a");
  });
});
