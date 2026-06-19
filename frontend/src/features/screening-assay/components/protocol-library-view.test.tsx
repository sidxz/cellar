import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { ProtocolLibraryView } from "./protocol-library-view";

// Radix Collapsible items need pointer-event stubs in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

const p = (over: Partial<Protocol>): Protocol =>
  ({
    id: "x",
    name: "X",
    protocol_type: "biochemical",
    status: "active",
    category: null,
    targets: [],
    readout_definitions: [],
    ontology_annotations: null,
    protocol_version: 1,
    ...over,
  }) as unknown as Protocol;

const data: Protocol[] = [
  p({ id: "a", name: "Active Bio", protocol_type: "biochemical", status: "active" }),
  p({ id: "b", name: "Cell One", protocol_type: "cell_based", status: "active" }),
  p({ id: "c", name: "Old One", protocol_type: "biochemical", status: "retired" }),
];

describe("ProtocolLibraryView", () => {
  it("pre-excludes retired protocols by default", () => {
    render(<ProtocolLibraryView protocols={data} />);
    expect(screen.getByText("Active Bio")).toBeInTheDocument();
    expect(screen.queryByText("Old One")).not.toBeInTheDocument();
  });

  it("filtering by a type facet narrows the list", () => {
    render(<ProtocolLibraryView protocols={data} />);
    // "Cell-Based" appears both as a facet value (role=checkbox) and as a row
    // type label — scope to the checkbox to avoid ambiguity.
    fireEvent.click(screen.getByRole("checkbox", { name: "Cell-Based" }));
    expect(screen.getByText("Cell One")).toBeInTheDocument();
    expect(screen.queryByText("Active Bio")).not.toBeInTheDocument();
  });
});
