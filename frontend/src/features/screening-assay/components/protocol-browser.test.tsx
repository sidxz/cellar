import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// Radix Tabs/Select need pointer-event stubs in jsdom.
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

vi.mock("../hooks/use-protocols", () => ({
  useProtocols: () => ({
    data: [
      {
        id: "a",
        name: "Alpha Bio",
        protocol_type: "biochemical",
        status: "active",
        category: null,
        targets: [],
        readout_definitions: [],
        ontology_annotations: null,
        protocol_version: 1,
      },
    ],
    isLoading: false,
    error: null,
  }),
}));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [] }),
}));
vi.mock("@/features/tagging/hooks/use-tags", () => ({
  useTags: () => ({ data: [] }),
}));
// AG Grid is heavy + jsdom-hostile; stub the grid to a simple list.
vi.mock("./protocol-grid", () => ({
  ProtocolGrid: ({ protocols }: { protocols?: { id: string; name: string }[] }) => (
    <div data-testid="grid">
      {protocols?.map((p) => (
        <div key={p.id}>{p.name}</div>
      ))}
    </div>
  ),
}));

import { ProtocolBrowser } from "./protocol-browser";

beforeEach(() => localStorage.clear());

describe("ProtocolBrowser", () => {
  it("defaults to the grid view", () => {
    render(<ProtocolBrowser />);
    expect(screen.getByTestId("grid")).toBeInTheDocument();
  });

  it("toggles to the library view and keeps the protocol visible", () => {
    render(<ProtocolBrowser />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: /library/i }));
    expect(screen.queryByTestId("grid")).not.toBeInTheDocument();
    expect(screen.getByText("Alpha Bio")).toBeInTheDocument();
  });
});
