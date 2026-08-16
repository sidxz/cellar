import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Header } from "./header";

const logoutMock = vi.fn();

vi.mock("@duar-auth/nextjs", () => ({
  useAuthz: () => ({
    user: { name: "Ada Lovelace", email: "ada@example.com" },
    logout: logoutMock,
  }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("./theme-toggle", () => ({ ThemeToggle: () => null }));
vi.mock("./font-size-control", () => ({ FontSizeControl: () => null }));

function openUserMenu() {
  fireEvent.keyDown(screen.getByRole("button", { name: /account menu/i }), { key: "Enter" });
}

describe("Header", () => {
  beforeEach(() => {
    logoutMock.mockClear();
    localStorage.clear();
  });

  it("shows the signed-in user's identity", () => {
    render(<Header />);
    expect(screen.getByText("AL")).toBeInTheDocument(); // initials
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("signs out via the user menu", () => {
    render(<Header />);
    openUserMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));
    expect(logoutMock).toHaveBeenCalled();
  });

  it("Switch workspace forgets the remembered workspace, then logs out", () => {
    localStorage.setItem("cellar.lastWorkspaceId", "ws-1");
    render(<Header />);
    openUserMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: /switch workspace/i }));
    expect(localStorage.getItem("cellar.lastWorkspaceId")).toBeNull();
    expect(logoutMock).toHaveBeenCalled();
  });
});
