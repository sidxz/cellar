import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Header } from "./header";

const logoutMock = vi.fn();

vi.mock("@sentinel-auth/nextjs", () => ({
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

describe("Header", () => {
  it("shows the signed-in user's identity", () => {
    render(<Header />);
    expect(screen.getByText("AL")).toBeInTheDocument(); // initials
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("signs out via the standalone logout button", () => {
    render(<Header />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logoutMock).toHaveBeenCalled();
  });
});
