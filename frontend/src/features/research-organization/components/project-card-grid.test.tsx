import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Project } from "../types";
import { ProjectCardGrid } from "./project-card-grid";

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));

const mk = (id: string, name: string): Project => ({
  id,
  workspace_id: "w",
  name,
  description: null,
  status: "active",
  created_by: "u",
  version: 1,
});

describe("ProjectCardGrid", () => {
  it("splits favorited projects into a Pinned section", () => {
    render(
      <ProjectCardGrid
        projects={[mk("a", "Alpha"), mk("b", "Beta")]}
        statsById={{}}
        favorites={new Set(["b"])}
        sort="name"
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText("Pinned")).toBeInTheDocument();
    expect(screen.getByText("All projects")).toBeInTheDocument();
  });

  it("shows the empty state when there are no projects", () => {
    render(
      <ProjectCardGrid
        projects={[]}
        statsById={{}}
        favorites={new Set()}
        sort="name"
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText("No projects")).toBeInTheDocument();
  });
});
