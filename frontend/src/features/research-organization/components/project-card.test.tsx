import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Project } from "../types";
import { ProjectCard } from "./project-card";

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));

const project: Project = {
  id: "p1",
  workspace_id: "w1",
  name: "Intramacrophage",
  description: null,
  status: "active",
  created_by: "u1",
  version: 1,
};

const stats = {
  molecule_count: 142,
  protocol_count: 3,
  run_count: 48,
  campaign_count: 3,
  last_activity_at: null,
  member_count: 0,
  member_ids: [],
};

describe("ProjectCard", () => {
  it("renders name, compounds and campaigns counts and a description fallback", () => {
    render(
      <ProjectCard
        project={project}
        stats={stats}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("Intramacrophage")).toBeInTheDocument();
    expect(screen.getByText("142")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("No description")).toBeInTheDocument();
  });

  it("toggles favorite without opening the project", () => {
    const onToggle = vi.fn();
    const onOpen = vi.fn();
    render(
      <ProjectCard
        project={project}
        stats={stats}
        favorited={false}
        onToggleFavorite={onToggle}
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByLabelText("Pin project"));
    expect(onToggle).toHaveBeenCalledWith(project, false);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("opens the project when the body is clicked", () => {
    const onOpen = vi.fn();
    render(
      <ProjectCard
        project={project}
        stats={stats}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByText("Intramacrophage"));
    expect(onOpen).toHaveBeenCalledWith(project);
  });

  it("shows em-dash counts when stats are undefined", () => {
    render(
      <ProjectCard
        project={project}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    // Both count cells (compounds + campaigns) fall back to an em-dash;
    // the last-activity slot also renders "—" via timeAgo(undefined).
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("renders the Archived badge and hides the pin button for archived projects", () => {
    render(
      <ProjectCard
        project={{ ...project, status: "archived" }}
        stats={stats}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.queryByLabelText("Pin project")).toBeNull();
    expect(screen.queryByLabelText("Unpin project")).toBeNull();
  });
});
