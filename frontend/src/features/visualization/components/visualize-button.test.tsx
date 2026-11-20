import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SavedViewSummary } from "../types";

const state = vi.hoisted(() => ({
  views: [] as SavedViewSummary[],
  useSavedViews: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("../hooks/use-saved-views", () => ({
  useSavedViews: (protocolId: string) => {
    state.useSavedViews(protocolId);
    return { data: state.views, isLoading: false };
  },
}));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [{ id: "proj-1", name: "NadD lead series" }] }),
}));

import { SavedViewsMenu, VisualizeButton } from "./visualize-button";

const view = (over: Partial<SavedViewSummary>): SavedViewSummary => ({
  id: "v1",
  name: "View",
  level: "wells",
  visibility: "private",
  created_by: "u1",
  can_edit: true,
  version: 1,
  protocols: [],
  ...over,
});

const openMenu = () =>
  fireEvent.keyDown(screen.getByRole("button", { name: "Saved views" }), { key: "Enter" });

beforeEach(() => {
  state.useSavedViews.mockReset();
  state.views = [];
});

describe("VisualizeButton", () => {
  it("on a protocol, lists its saved views only once the menu opens", () => {
    state.views = [
      view({ id: "v1", name: "Plate QC" }),
      view({ id: "v2", name: "Potency by batch", visibility: "project", project_id: "proj-1" }),
    ];
    render(<VisualizeButton protocolId="p1" />);
    expect(screen.getByRole("button", { name: "Visualize" })).toBeInTheDocument();
    expect(state.useSavedViews).not.toHaveBeenCalled();

    openMenu();
    expect(state.useSavedViews).toHaveBeenCalledWith("p1");
    const qc = screen.getByRole("menuitem", { name: /Plate QC/ });
    expect(qc).toHaveAttribute("href", "/assays/visualize/v1");
    expect(qc).toHaveTextContent("Private");
    const potency = screen.getByRole("menuitem", { name: /Potency by batch/ });
    expect(potency).toHaveAttribute("href", "/assays/visualize/v2");
    expect(potency).toHaveTextContent("NadD lead series");
  });

  it("lists no view when the protocol has no saved views", () => {
    render(<VisualizeButton protocolId="p1" />);
    openMenu();
    const hrefs = screen.getAllByRole("menuitem").map((i) => i.getAttribute("href") ?? "");
    expect(hrefs).toContain("/assays/visualize");
    expect(hrefs.filter((h) => h.startsWith("/assays/visualize/"))).toEqual([]);
  });

  it("links to every saved view the chemist can see", () => {
    state.views = [view({ id: "v1", name: "Plate QC" })];
    render(<VisualizeButton protocolId="p1" />);
    openMenu();
    expect(screen.getByRole("menuitem", { name: "All saved views" })).toHaveAttribute(
      "href",
      "/assays/visualize",
    );
  });

  it("marks the view that is open", () => {
    state.views = [view({ id: "v1", name: "Plate QC" }), view({ id: "v2", name: "Potency" })];
    render(<SavedViewsMenu protocolId="p1" current="v2" />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Views" }), { key: "Enter" });
    expect(screen.getByRole("menuitem", { name: /Potency/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("menuitem", { name: /Plate QC/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("menuitem", { name: "All saved views" })).toBeInTheDocument();
  });

  it("on a run, is a plain link with no menu", () => {
    render(<VisualizeButton runId="r1" />);
    expect(screen.getByRole("link", { name: "Visualize" })).toHaveAttribute(
      "href",
      "/assays/visualize?run=r1",
    );
    expect(screen.queryByRole("button", { name: "Saved views" })).not.toBeInTheDocument();
  });
});
