import type { AuthzWorkspaceSelectorProps } from "@sentinel-auth/nextjs";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkspaceSelector } from "./workspace-selector";

// Typed against the SDK prop so role stays valid if WorkspaceRole is a union.
const WORKSPACES: AuthzWorkspaceSelectorProps["workspaces"] = [
  { id: "ws-1", name: "Alpha Lab", slug: "alpha-lab", role: "admin" },
  { id: "ws-2", name: "Beta Lab", slug: "beta-lab", role: "viewer" },
];

const KEY = "cellar.lastWorkspaceId";

describe("WorkspaceSelector", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("auto-selects the remembered workspace and shows an opening state instead of the picker", () => {
    localStorage.setItem(KEY, "ws-2");
    const onSelect = vi.fn();
    render(<WorkspaceSelector workspaces={WORKSPACES} onSelect={onSelect} isLoading={false} />);
    expect(onSelect).toHaveBeenCalledWith("ws-2");
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/entering beta lab/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /alpha lab/i })).not.toBeInTheDocument();
  });

  it("shows the picker when the remembered workspace is no longer in the list", () => {
    localStorage.setItem(KEY, "ws-gone");
    const onSelect = vi.fn();
    render(<WorkspaceSelector workspaces={WORKSPACES} onSelect={onSelect} isLoading={false} />);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /alpha lab/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /beta lab/i })).toBeInTheDocument();
  });

  it("shows the picker when nothing is remembered", () => {
    const onSelect = vi.fn();
    render(<WorkspaceSelector workspaces={WORKSPACES} onSelect={onSelect} isLoading={false} />);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /alpha lab/i })).toBeInTheDocument();
  });

  it("remembers a manual pick before selecting it", () => {
    const onSelect = vi.fn();
    render(<WorkspaceSelector workspaces={WORKSPACES} onSelect={onSelect} isLoading={false} />);
    fireEvent.click(screen.getByRole("button", { name: /alpha lab/i }));
    expect(localStorage.getItem(KEY)).toBe("ws-1");
    expect(onSelect).toHaveBeenCalledWith("ws-1");
  });
});
